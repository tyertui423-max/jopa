Add-Type -Path "C:\Users\tyert\.nuget\packages\cmllib.core\4.0.6\lib\netstandard2.0\CmlLib.Core.dll"
$methods = [CmlLib.Core.MinecraftLauncher].GetMethods()
foreach ($m in $methods) {
    if ($m.Name -like "*Process*" -or $m.Name -like "*Launch*" -or $m.Name -like "*Install*") {
        Write-Host "$($m.ReturnType.Name) $($m.Name)($([string]::Join(', ', ($m.GetParameters() | ForEach-Object { $_.ParameterType.Name + ' ' + $_.Name }))))"
    }
}
