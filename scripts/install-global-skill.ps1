[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Position = 0)]
    [string]$SkillName = "repo-agent-bootstrap",

    [Parameter()]
    [string]$SourcePath,

    [Parameter()]
    [string]$GlobalSkillsRoot = (Join-Path $HOME ".agents\skills"),

    [Parameter()]
    [ValidateSet("Junction", "SymbolicLink", "Copy")]
    [string]$InstallMode = "Junction",

    [Parameter()]
    [switch]$MirrorToCodex,

    [Parameter()]
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-AbsolutePath {
    param([Parameter(Mandatory = $true)][string]$PathValue)

    if ([System.IO.Path]::IsPathRooted($PathValue)) {
        return [System.IO.Path]::GetFullPath($PathValue)
    }

    return [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $PathValue))
}

function Get-DefaultSourcePath {
    param([Parameter(Mandatory = $true)][string]$Name)

    $candidates = @(
        (Join-Path (Get-Location) ".github\skills\$Name"),
        (Join-Path (Get-Location) "skills\$Name")
    )

    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath (Join-Path $candidate "SKILL.md")) {
            return [System.IO.Path]::GetFullPath($candidate)
        }
    }

    throw "Could not find a skill named '$Name' under .github\skills\ or skills\ in the current repository."
}

function Assert-SkillSource {
    param([Parameter(Mandatory = $true)][string]$PathValue)

    $skillFile = Join-Path $PathValue "SKILL.md"
    if (-not (Test-Path -LiteralPath $PathValue -PathType Container)) {
        throw "Skill source directory does not exist: $PathValue"
    }
    if (-not (Test-Path -LiteralPath $skillFile -PathType Leaf)) {
        throw "Skill source is missing SKILL.md: $skillFile"
    }
}

function Remove-ExistingTarget {
    param(
        [Parameter(Mandatory = $true)][string]$TargetPath,
        [Parameter(Mandatory = $true)][bool]$AllowRemoval
    )

    if (-not (Test-Path -LiteralPath $TargetPath)) {
        return $true
    }

    if (-not $AllowRemoval) {
        if ($WhatIfPreference) {
            Write-Host "What if: target already exists and would require -Force to replace: $TargetPath"
            return $false
        }
        throw "Target already exists: $TargetPath. Re-run with -Force to replace it."
    }

    if ($PSCmdlet.ShouldProcess($TargetPath, "Remove existing target")) {
        Remove-Item -LiteralPath $TargetPath -Recurse -Force
    }

    return $true
}

function Install-SkillTarget {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Target,
        [Parameter(Mandatory = $true)][string]$Mode,
        [Parameter(Mandatory = $true)][bool]$AllowRemoval
    )

    $targetParent = Split-Path -Parent $Target
    if (-not (Test-Path -LiteralPath $targetParent -PathType Container)) {
        if ($PSCmdlet.ShouldProcess($targetParent, "Create parent directory")) {
            New-Item -ItemType Directory -Path $targetParent -Force | Out-Null
        }
    }

    $canInstall = Remove-ExistingTarget -TargetPath $Target -AllowRemoval:$AllowRemoval
    if (-not $canInstall) {
        return
    }

    switch ($Mode) {
        "Copy" {
            if ($PSCmdlet.ShouldProcess($Target, "Copy skill from $Source")) {
                Copy-Item -LiteralPath $Source -Destination $Target -Recurse
            }
        }
        "Junction" {
            if ($PSCmdlet.ShouldProcess($Target, "Create junction to $Source")) {
                New-Item -ItemType Junction -Path $Target -Target $Source | Out-Null
            }
        }
        "SymbolicLink" {
            if ($PSCmdlet.ShouldProcess($Target, "Create symbolic link to $Source")) {
                New-Item -ItemType SymbolicLink -Path $Target -Target $Source | Out-Null
            }
        }
        default {
            throw "Unsupported install mode: $Mode"
        }
    }
}

$resolvedSourcePath = if ($SourcePath) {
    Resolve-AbsolutePath -PathValue $SourcePath
}
else {
    Get-DefaultSourcePath -Name $SkillName
}

Assert-SkillSource -PathValue $resolvedSourcePath

$resolvedGlobalSkillsRoot = Resolve-AbsolutePath -PathValue $GlobalSkillsRoot
$globalTarget = Join-Path $resolvedGlobalSkillsRoot $SkillName

Install-SkillTarget `
    -Source $resolvedSourcePath `
    -Target $globalTarget `
    -Mode $InstallMode `
    -AllowRemoval:$Force.IsPresent

if ($MirrorToCodex) {
    $codexRoot = Join-Path $HOME ".codex\skills"
    $codexTarget = Join-Path $codexRoot $SkillName
    Install-SkillTarget `
        -Source $resolvedSourcePath `
        -Target $codexTarget `
        -Mode $InstallMode `
        -AllowRemoval:$Force.IsPresent
}

$summary = [ordered]@{
    skillName = $SkillName
    source = $resolvedSourcePath
    globalTarget = $globalTarget
    installMode = $InstallMode
    mirroredToCodex = [bool]$MirrorToCodex
}

$summary | ConvertTo-Json -Depth 4
