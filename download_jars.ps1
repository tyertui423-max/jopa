$clientJarUrl = "https://www.dropbox.com/scl/fi/ckl7cnyc5myu45qouj3pt/DanyaClient-3.0.14.jar?rlkey=ktigpmtb9cuxa4wzk9ilxzw57&st=w10dcf13&dl=1"
$apiJarUrl = "https://www.dropbox.com/scl/fi/dm3ukfji3acn9bpikt8sw/fabric-api-0.161.0-26.2.jar?rlkey=edqw7zj6rt7be4bmc6qo58d1r&st=zxfcxmg2&dl=1"

$dir = "c:\Users\tyert\OneDrive\Desktop\inoagent site\jars"
if (!(Test-Path $dir)) {
    New-Item -ItemType Directory -Path $dir | Out-Null
}

$clientFile = Join-Path $dir "DanyaClient-3.0.14.jar"
$apiFile = Join-Path $dir "fabric-api-0.161.0-26.2.jar"

Write-Host "Downloading DanyaClient-3.0.14.jar..."
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
(New-Object System.Net.WebClient).DownloadFile($clientJarUrl, $clientFile)

Write-Host "Downloading fabric-api-0.161.0-26.2.jar..."
(New-Object System.Net.WebClient).DownloadFile($apiJarUrl, $apiFile)

Write-Host "Checking downloaded files:"
Get-ChildItem $dir | Select-Object Name, Length
