<#
.SYNOPSIS
  Finetune a SmolVLA policy on the SO-101 pick-cube demonstrations, with flexible
  checkpointing, resume, and Weights & Biases logging.

.DESCRIPTION
  Wraps `lerobot-train` (run via the venv python) with sensible defaults for the
  locally recorded `aakashv100/so101-pick-cube-v2` dataset (50 episodes, 2 cameras,
  6-DoF state/action, 30 fps).

  Unlike train_act.ps1 (which trains from random init), this finetunes the
  pretrained `lerobot/smolvla_base` checkpoint via --policy.path, so the policy
  config, camera features and processors come from the checkpoint and only the
  normalizer stats are recomputed from the dataset. The base config keeps the VLM
  and vision encoder frozen and trains the action expert, which is both the
  reference finetune recipe and what keeps this inside 16 GB of VRAM.

  Two consequences of finetuning smolvla_base that this script handles for you:

  - The base checkpoint declares its cameras as observation.images.camera{1,2,3}.
    Our dataset records top_cam + gripper_cam, so -RenameMap maps them onto the
    first two slots (camera3 is simply absent). The map is baked into the saved
    preprocessor, so eval needs no extra flags.
  - lerobot turns --policy.path into a Path, which mangles a Hub repo id into
    'lerobot\smolvla_base' on Windows. The base checkpoint is therefore
    downloaded to pretrained-model/ first and passed as a local directory.

  Checkpoints land in outputs/train/<JobName>/checkpoints, saved every -SaveFreq
  steps plus a rolling `last` symlink. Resume with -Resume (optionally -ResumeFrom).

  Validation is off by default. -ValEpisodes holds whole episodes out of training and scores the
  policy's own loss on them every -ValFreq steps, logged as `val/loss`. Every frame of every
  held-out episode is scored, so nothing is capped per episode. Measured on this machine, a pass
  runs at ~19 frames/s (video decode bound, num_workers=0), so 10 held-out episodes of ~1,200
  frames cost ~10 min each time: -ValFreq 2000 adds ~1.7 h to a 20k-step run. Raise it to trade
  curve resolution for wall-clock. Note that normalizer stats still come from the whole dataset,
  so this measures generalization to unseen episodes, not to an unseen data distribution.

  NOTE on Windows: keep -NumWorkers 0. Measured 2026-07-31 with -NumWorkers 2 -PrefetchFactor 2
  and persistent workers off: the trainer deadlocks at step 0, having burned no CPU time at all
  after six minutes, and the worker processes never appear. So persistent workers are not the
  cause and -PersistentWorkers does not work around it; both flags exist only to re-test this on
  a future torch/Windows build. They reach the trainer only when -NumWorkers > 0, which is the
  only case lerobot honours them in.

  NOTE on -Bf16: lerobot builds its Accelerator without a mixed_precision argument and never
  passes --policy.use_amp to it, so training is fp32 unless the ACCELERATE_MIXED_PRECISION
  environment variable is set, which is what -Bf16 does. Measured over 200 steps on the RTX 5080
  Laptop at batch 16: no gain (updt_s 0.506 bf16 vs 0.481 fp32), so this workload is not
  matmul-bound at this batch size. The flag is kept for larger batches, where it may pay off.

.EXAMPLE
  # Short smoke run to confirm the pipeline and measure VRAM before committing
  .\scripts\train_smolvla.ps1 -Steps 200 -SaveFreq 100 -JobName smolvla_smoke

.EXAMPLE
  # Full finetune with W&B logging
  .\scripts\train_smolvla.ps1 -Wandb -WandbProject so101-smolvla

.EXAMPLE
  # Finetune on episodes 0-39 and track the loss on the 10 held-out episodes
  .\scripts\train_smolvla.ps1 -ValEpisodes (40..49) -Wandb -JobName smolvla_holdout

.EXAMPLE
  # Resume the last checkpoint and keep logging to the same W&B run
  .\scripts\train_smolvla.ps1 -Resume -Wandb -WandbRunId abc123
#>
[CmdletBinding()]
param(
    # --- data / model ---
    [string]$RepoId      = "aakashv100/so101-pick-cube-v2",
    [string]$DatasetRoot = "",                            # default: the LeRobot cache dir for -RepoId; pass "" to download from the Hub
    [string]$BaseModel   = "lerobot/smolvla_base",        # pretrained checkpoint to finetune (Hub id or local dir)
    # Dataset camera keys -> the camera slots smolvla_base was pretrained with.
    [string]$RenameMap   = "{observation.images.top_cam: observation.images.camera1, " +
                           "observation.images.gripper_cam: observation.images.camera2}",
    [string]$JobName     = "smolvla_so101_pick_cube",
    [string]$OutputDir   = "",                            # default: outputs/train/<JobName>
    [string]$Device      = "cuda",                        # cuda | cpu
    [int]$BatchSize      = 16,                            # ~5 GB VRAM with the VLM frozen; 20k steps ~= 5.3 epochs
    [int]$Steps          = 20000,
    [int]$ChunkSize      = 50,                            # smolvla_base native chunk (~1.7 s @ 30 fps)
    [int]$ActionSteps    = 50,                            # actions executed per query; lower = more closed-loop
    [int]$DecaySteps     = 0,                             # LR decay horizon (default: -Steps)
    [int]$NumWorkers     = 0,                             # keep 0 on Windows (see -PersistentWorkers)
    [int]$Seed           = 1000,                          # lerobot's default; vary to measure run-to-run spread
    [switch]$Bf16,                                        # bf16 mixed precision; measured no speedup here (see NOTE)
    [switch]$PersistentWorkers,                           # only has an effect with -NumWorkers > 0
    [int]$PrefetchFactor = 4,                             # batches prefetched per worker; -NumWorkers > 0 only
    [switch]$ReturnUint8,                                 # faster dataloading; unverified against SmolVLA's IDENTITY visual norm
    [switch]$Augment,                                     # enable image augmentation (color/affine jitter)

    # --- validation ---
    # Episodes held out of training and scored as a validation loss, e.g. -ValEpisodes (40..49).
    # The split is by whole episode and every frame of each held-out episode is scored, so the
    # metric is not truncated per episode. Empty = no validation (the historical behaviour).
    [int[]]$ValEpisodes  = @(),
    [int]$ValFreq        = 2000,                          # validate every N steps (and at the last step)

    # --- checkpointing / logging cadence ---
    [int]$SaveFreq       = 2000,
    [int]$LogFreq        = 200,
    [switch]$NoSaveCheckpoint,                            # disable checkpointing entirely

    # --- resume ---
    [switch]$Resume,
    [string]$ResumeFrom  = "",                            # checkpoint dir (default: <OutputDir>/checkpoints/last)

    # --- weights & biases ---
    [switch]$Wandb,
    [string]$WandbProject = "so101-smolvla",
    [string]$WandbEntity  = "",
    [string]$WandbRunId   = "",                           # set to continue an existing run on resume
    [string]$WandbNotes   = "",
    [string]$WandbMode    = "online",                     # online | offline | disabled

    # --- hub ---
    [switch]$PushToHub
)

$ErrorActionPreference = "Stop"

# Run from the repo root (parent of this script's folder) so relative paths resolve.
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "venv python not found at $Python. Activate/create the project venv first."
}

# Force UTF-8 so console logging (e.g. the 'pi' symbol) doesn't crash on cp1252 Windows shells.
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

# accelerate reads its precision from this variable and lerobot never sets it, so it is the only
# hook for mixed precision. Assigned unconditionally: a stale "bf16" from an earlier call in the
# same shell would otherwise silently apply to an fp32 run.
$env:ACCELERATE_MIXED_PRECISION = if ($Bf16) { "bf16" } else { "no" }

function Resolve-BaseModel([string]$Model) {
    <#
      Return a local directory holding $Model. lerobot's parser wraps
      --policy.path in a Path, which rewrites "lerobot/smolvla_base" as
      "lerobot\smolvla_base" on Windows and then fails Hub validation, so a Hub
      id has to be materialised on disk before we can point the trainer at it.
    #>
    if (Test-Path (Join-Path $Model "config.json")) {
        return $Model
    }
    $local = Join-Path "pretrained-model" ($Model -split "/")[-1]
    if (-not (Test-Path (Join-Path $local "config.json"))) {
        Write-Host "Downloading $Model -> $local" -ForegroundColor Yellow
        # hf_hub writes its progress bars to stderr; don't let that abort the run.
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        $PSNativeCommandUseErrorActionPreference = $false
        & $Python -c "import sys; from huggingface_hub import snapshot_download; snapshot_download(sys.argv[1], local_dir=sys.argv[2])" $Model $local
        $downloadExit = $LASTEXITCODE
        $ErrorActionPreference = $prevEap
        if ($downloadExit -ne 0) { throw "Failed to download $Model from the Hub." }
    }
    if (-not (Test-Path (Join-Path $local "config.json"))) {
        throw "$Model downloaded to $local but no config.json is there."
    }
    return $local
}

if ([string]::IsNullOrEmpty($OutputDir)) {
    $OutputDir = "outputs/train/$JobName"
}
# v2 was recorded straight into the LeRobot cache rather than hf_data/.
if (-not $PSBoundParameters.ContainsKey("DatasetRoot")) {
    $DatasetRoot = Join-Path $env:USERPROFILE ".cache\huggingface\lerobot\$($RepoId -replace '/', '\')"
}
if ($DecaySteps -le 0) {
    # Match the LR decay horizon to the run length; the base config assumes 30k steps.
    $DecaySteps = $Steps
}

$saveCkpt = if ($NoSaveCheckpoint) { "false" } else { "true" }
$pushHub  = if ($PushToHub)        { "true" }  else { "false" }

$cmd = @(
    "-m", "lerobot.scripts.lerobot_train",
    "--policy.device=$Device",
    "--policy.push_to_hub=$pushHub",
    "--policy.chunk_size=$ChunkSize",
    "--policy.n_action_steps=$ActionSteps",
    "--policy.scheduler_decay_steps=$DecaySteps",
    "--dataset.repo_id=$RepoId",
    "--batch_size=$BatchSize",
    "--steps=$Steps",
    "--save_checkpoint=$saveCkpt",
    "--save_freq=$SaveFreq",
    "--log_freq=$LogFreq",
    "--num_workers=$NumWorkers",
    "--seed=$Seed",
    "--job_name=$JobName",
    "--output_dir=$OutputDir",
    "--rename_map=$RenameMap"
)

# lerobot only honours these when num_workers > 0, so passing them otherwise just adds noise.
if ($NumWorkers -gt 0) {
    $cmd += "--persistent_workers=$(if ($PersistentWorkers) { 'true' } else { 'false' })"
    $cmd += "--prefetch_factor=$PrefetchFactor"
}

# Use the local dataset tree when provided (avoids re-downloading from the Hub).
if (-not [string]::IsNullOrEmpty($DatasetRoot)) {
    $cmd += "--dataset.root=$DatasetRoot"
}

if ($ReturnUint8) {
    $cmd += "--dataset.return_uint8=true"
}

# Held-out validation. The training split becomes every remaining episode, so the policy never
# sees a validation frame, and the loss is comparable across steps because the pass is sequential
# and unaugmented.
if ($ValEpisodes.Count -gt 0) {
    $cmd += "--dataset.val_episodes=[$($ValEpisodes -join ',')]"
    $cmd += "--val_freq=$ValFreq"
}

# Enable the image_transforms already defined in the dataset config (brightness/contrast/
# saturation/hue/sharpness/affine). Off by default; turn on for closed-loop robustness.
if ($Augment) {
    $cmd += "--dataset.image_transforms.enable=true"
}

# --- Weights & Biases ---
if ($Wandb) {
    $cmd += "--wandb.enable=true"
    $cmd += "--wandb.project=$WandbProject"
    $cmd += "--wandb.mode=$WandbMode"
    if (-not [string]::IsNullOrEmpty($WandbEntity)) { $cmd += "--wandb.entity=$WandbEntity" }
    if (-not [string]::IsNullOrEmpty($WandbRunId))  { $cmd += "--wandb.run_id=$WandbRunId" }
    if (-not [string]::IsNullOrEmpty($WandbNotes))  { $cmd += "--wandb.notes=$WandbNotes" }
} else {
    $cmd += "--wandb.enable=false"
}

# --- Resume vs fresh finetune ---
# On resume, lerobot loads the checkpoint's train_config.json and applies the
# above flags as overrides, so changing -Steps/-SaveFreq/-Wandb* here works.
# --policy.path must be dropped: the weights come from the checkpoint, not the base model.
if ($Resume) {
    $ckptDir = if (-not [string]::IsNullOrEmpty($ResumeFrom)) { $ResumeFrom } else { "$OutputDir/checkpoints/last" }
    $configPath = "$ckptDir/pretrained_model/train_config.json"
    if (-not (Test-Path $configPath)) {
        throw "Cannot resume: $configPath not found. Check -OutputDir/-ResumeFrom (need a saved checkpoint)."
    }
    $cmd += "--resume=true"
    $cmd += "--config_path=$configPath"
} else {
    $cmd += "--policy.path=$(Resolve-BaseModel $BaseModel)"
}

Write-Host "=== Finetuning SmolVLA ($(if ($Resume) { 'resume' } else { "from $BaseModel" })) ===" -ForegroundColor Cyan
Write-Host "dataset : $RepoId  (root: $(if ($DatasetRoot) { $DatasetRoot } else { 'Hub' }))"
Write-Host "output  : $OutputDir"
Write-Host "device  : $Device   steps: $Steps   batch: $BatchSize   save_freq: $SaveFreq"
Write-Host "precision: $env:ACCELERATE_MIXED_PRECISION   seed: $Seed   workers: $NumWorkers$(if ($NumWorkers -gt 0) { " (persistent=$($PersistentWorkers.IsPresent), prefetch=$PrefetchFactor)" })"
Write-Host "chunk   : $ChunkSize   n_action_steps: $ActionSteps   lr_decay_steps: $DecaySteps"
Write-Host "val     : $(if ($ValEpisodes.Count -gt 0) { "$($ValEpisodes.Count) held-out episodes every $ValFreq steps" } else { 'disabled' })"
Write-Host "cameras : $RenameMap"
Write-Host "wandb   : $(if ($Wandb) { "$WandbProject (mode=$WandbMode)" } else { 'disabled' })"
Write-Host ""
Write-Host "$Python $($cmd -join ' ')" -ForegroundColor DarkGray
Write-Host ""

# Python logging writes warnings to stderr; don't let that abort the run.
$ErrorActionPreference = "Continue"
$PSNativeCommandUseErrorActionPreference = $false

& $Python @cmd
exit $LASTEXITCODE
