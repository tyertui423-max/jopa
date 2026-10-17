$testDir = "c:\Users\tyert\OneDrive\Desktop\inoagent site\jars\test_client"
if (!(Test-Path $testDir)) {
    New-Item -ItemType Directory -Path $testDir | Out-Null
}

$launcherProfiles = Join-Path $testDir "launcher_profiles.json"
Set-Content -Path $launcherProfiles -Value '{"profiles": {}}'

$installer = "c:\Users\tyert\OneDrive\Desktop\inoagent site\jars\fabric-installer.jar"
Write-Host "Running fabric installer..."
& java -jar $installer client -mcversion 26.2 -loader 0.19.5 -dir $testDir

Write-Host "Installed files in versions:"
Get-ChildItem (Join-Path $testDir "versions") -Recurse | Select-Object Name, Length
