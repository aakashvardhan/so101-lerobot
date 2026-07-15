<#
.SYNOPSIS
  Run ACT policy inference on the SO-101 for the eval scoresheet, with optional
  cache clearing and easily overridable parameters.

.DESCRIPTION
  Wraps `lerobot-record` (run via the venv python) with the eval defaults for
  the ACT_eval_scoresheet.xlsx protocol: 50 episodes, both USB cameras, the
  act_so101_pick_cube_v2 checkpoint, AMP on, camera display on.

  -Mode picks the scoresheet tab (fixed | random) and sets the eval dataset
  repo id accordingly. -ClearCache deletes that dataset's local HF cache dir
  first, so a crashed run can be restarted cleanly.

  Keyboard during recording: right-arrow ends the episode and saves,
  Escape stops without saving.

.EXAMPLE
  # Fixed-position tab, fresh start
  .\scripts\run_eval.ps1 -Mode fixed -ClearCache

.EXAMPLE
  # Random-position tab
  .\scripts\run_eval.ps1 -Mode random -ClearCache

.EXAMPLE
  # Try a different checkpoint for a quick 5-episode sanity run
  .\scripts\run_eval.ps1 -Mode fixed -Checkpoint outputs/train/act_so101_pick_cube_v2/checkpoints/030000/pretrained_model -NumEpisodes 5 -RepoId aakashv100/eval_sanity -ClearCache
#>
[CmdletBinding()]
param(
    # --- eval protocol ---
    [ValidateSet("fixed", "random")]
    [string]$Mode        = "fixed",
    [string]$RepoId      = "",                            # default: aakashv100/eval_so101-pick-cube-v2-<Mode>
    [int]$NumEpisodes    = 50,
    [string]$Task        = "Pick up the cube and place it in the bowl",
    [switch]$ClearCache,                                  # delete the eval dataset's local HF cache before running
    [switch]$Resume,                                      # continue an interrupted run; -NumEpisodes = episodes to add THIS session

    # --- model ---
    [string]$Checkpoint  = "outputs/train/act_so101_pick_cube_v2/checkpoints/060000/pretrained_model",
    [string]$Device      = "cuda",                        # cuda | cpu
    [switch]$NoAmp,                                       # disable mixed-precision inference

    # --- robot / cameras ---
    [string]$Port        = "COM3",
    [string]$RobotId     = "my_so_arm",
    [string]$CalibDir    = "./calibration/robots/so_follower",
    [int]$GripperCamIndex = 0,
    [int]$TopCamIndex     = 1,
    [int]$Fps             = 30,
    [switch]$NoDisplay,                                   # hide the side-by-side camera window
    [switch]$NoReturnToStart,                             # don't drive the arm back to its start pose after each episode

    # --- timing (seconds; 0 = keep lerobot defaults) ---
    [int]$EpisodeTime    = 0,
    [int]$ResetTime      = 0
)

$ErrorActionPreference = "Stop"

# Run from the repo root (parent of this script's folder) so relative paths resolve.
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "venv python not found at $Python. Activate/create the project venv first."
}

# Force UTF-8 so console logging doesn't crash on cp1252 Windows shells.
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

if ([string]::IsNullOrEmpty($RepoId)) {
    $RepoId = "aakashv100/eval_so101-pick-cube-v2-$Mode"
}
if ($RepoId -notmatch "/eval_") {
    throw "Eval dataset repo_id must start with 'eval_' after the user name (got '$RepoId')."
}
if (-not (Test-Path "$Checkpoint/config.json")) {
    throw "Checkpoint not found: $Checkpoint (need the pretrained_model dir)."
}

# --- Clear the local HF cache for this eval dataset ---
$CacheDir = Join-Path $env:USERPROFILE ".cache\huggingface\lerobot\$($RepoId -replace '/', '\')"
if ($Resume) {
    if ($ClearCache) { throw "-Resume and -ClearCache are mutually exclusive." }
    if (-not (Test-Path $CacheDir)) {
        throw "Nothing to resume: no cache at $CacheDir"
    }
    Write-Host "Resuming into existing dataset ($CacheDir); recording $NumEpisodes MORE episodes." -ForegroundColor Yellow
} elseif ($ClearCache) {
    if (Test-Path $CacheDir) {
        Write-Host "Clearing cache: $CacheDir" -ForegroundColor Yellow
        Remove-Item -Recurse -Force -Confirm:$false $CacheDir
    } else {
        Write-Host "Cache already clean: $CacheDir" -ForegroundColor DarkGray
    }
} elseif (Test-Path $CacheDir) {
    throw "Cache dir exists from a previous run: $CacheDir`nRe-run with -ClearCache to delete it, -Resume to continue it, or pass a different -RepoId."
}

$useAmp  = if ($NoAmp)           { "false" } else { "true" }
$display = if ($NoDisplay)       { "false" } else { "true" }
$goHome  = if ($NoReturnToStart) { "false" } else { "true" }

$cameras = "{gripper_cam: {type: opencv, index_or_path: $GripperCamIndex, width: 640, height: 480, fps: $Fps, fourcc: MJPG}, " +
           "top_cam: {type: opencv, index_or_path: $TopCamIndex, width: 640, height: 480, fps: $Fps, fourcc: MJPG}}"

$cmd = @(
    "-m", "lerobot.scripts.lerobot_record",
    "--robot.type=so101_follower",
    "--robot.port=$Port",
    "--robot.id=$RobotId",
    "--robot.calibration_dir=$CalibDir",
    "--robot.cameras=$cameras",
    "--policy.path=$Checkpoint",
    "--policy.device=$Device",
    "--policy.use_amp=$useAmp",
    "--dataset.repo_id=$RepoId",
    "--dataset.num_episodes=$NumEpisodes",
    "--dataset.single_task=$Task",
    "--display_cameras=$display",
    "--return_to_start_pose=$goHome"
)

if ($EpisodeTime -gt 0) { $cmd += "--dataset.episode_time_s=$EpisodeTime" }
if ($ResetTime -gt 0)   { $cmd += "--dataset.reset_time_s=$ResetTime" }
if ($Resume) {
    $cmd += "--resume=true"
    # resume() refuses to run without an explicit root (it must not write into
    # the Hub snapshot cache); point it at the dataset's recording cache dir.
    $cmd += "--dataset.root=$CacheDir"
}

Write-Host "=== ACT eval inference ($Mode tab) ===" -ForegroundColor Cyan
Write-Host "checkpoint : $Checkpoint"
Write-Host "dataset    : $RepoId   episodes: $NumEpisodes"
Write-Host "cameras    : gripper=$GripperCamIndex  top=$TopCamIndex  @ ${Fps}fps"
Write-Host "amp        : $useAmp   display: $display"
Write-Host ""
Write-Host "$Python $($cmd -join ' ')" -ForegroundColor DarkGray
Write-Host ""

# Python logging writes warnings to stderr; don't let that abort the run.
$ErrorActionPreference = "Continue"
$PSNativeCommandUseErrorActionPreference = $false

& $Python @cmd
exit $LASTEXITCODE
