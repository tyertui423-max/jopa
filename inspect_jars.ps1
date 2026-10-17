Add-Type -AssemblyName System.IO.Compression.FileSystem

$dir = "c:\Users\tyert\OneDrive\Desktop\inoagent site\jars"
$jars = @("DanyaClient-3.0.14.jar", "fabric-api-0.161.0-26.2.jar")

foreach ($jarName in $jars) {
    $jarPath = Join-Path $dir $jarName
    Write-Host "=== $jarName ==="
    $zip = [System.IO.Compression.ZipFile]::OpenRead($jarPath)
    $entry = $zip.GetEntry("fabric.mod.json")
    if ($entry) {
        $stream = $entry.Open()
        $reader = New-Object System.IO.StreamReader($stream)
        $json = $reader.ReadToEnd()
        Write-Host $json
        $reader.Close()
        $stream.Close()
    } else {
        Write-Host "No fabric.mod.json found"
    }
    $zip.Dispose()
    Write-Host ""
}
