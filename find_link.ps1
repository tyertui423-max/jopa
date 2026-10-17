$html = [System.IO.File]::ReadAllText("c:\Users\tyert\OneDrive\Desktop\inoagent site\jars\fabric-api-0.161.0-26.2.jar")
$matches = [regex]::Matches($html, 'https://[a-zA-Z0-9\.\-_/%\?&=]+')
foreach ($m in $matches) {
    if ($m.Value -like "*fabric-api*" -or $m.Value -like "*dropboxusercontent*") {
        Write-Host $m.Value
    }
}
