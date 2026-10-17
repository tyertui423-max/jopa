$src = "c:\Users\tyert\OneDrive\Desktop\inoagent site\loader_src"
$dest = "c:\Users\tyert\OneDrive\Desktop\INOAGENT LOADER"
$siteJars = "c:\Users\tyert\OneDrive\Desktop\inoagent site\jars"

New-Item -ItemType Directory -Force -Path $dest | Out-Null

Copy-Item "$src\DanyaClientLoader.csproj" "$dest\DanyaClientLoader.csproj" -Force
Copy-Item "$src\App.xaml" "$dest\App.xaml" -Force
Copy-Item "$src\App.xaml.cs" "$dest\App.xaml.cs" -Force
Copy-Item "$src\MainWindow.xaml" "$dest\MainWindow.xaml" -Force
Copy-Item "$src\MainWindow.xaml.cs" "$dest\MainWindow.xaml.cs" -Force
Copy-Item "$src\MinecraftLauncherService.cs" "$dest\MinecraftLauncherService.cs" -Force

New-Item -ItemType Directory -Force -Path "$dest\ui" | Out-Null
Copy-Item "$src\ui\index.html" "$dest\ui\index.html" -Force
Copy-Item "$src\ui\style.css" "$dest\ui\style.css" -Force
Copy-Item "$src\ui\app.js" "$dest\ui\app.js" -Force

New-Item -ItemType Directory -Force -Path "$dest\ui\assets" | Out-Null
if (Test-Path "$dest\assets\logo.png") { Copy-Item "$dest\assets\logo.png" "$dest\ui\assets\logo.png" -Force }
if (Test-Path "$dest\assets\mc_26_banner.jpg") { Copy-Item "$dest\assets\mc_26_banner.jpg" "$dest\ui\assets\mc_26_banner.jpg" -Force }

# Copy pre-downloaded jars
New-Item -ItemType Directory -Force -Path "$dest\jars" | Out-Null
if (Test-Path "$siteJars\DanyaClient-3.0.14.jar") {
    Copy-Item "$siteJars\DanyaClient-3.0.14.jar" "$dest\jars\DanyaClient-3.0.14.jar" -Force
}
if (Test-Path "$siteJars\fabric-api-0.161.0-26.2.jar") {
    Copy-Item "$siteJars\fabric-api-0.161.0-26.2.jar" "$dest\jars\fabric-api-0.161.0-26.2.jar" -Force
}
if (Test-Path "$siteJars\fabric-installer.jar") {
    Copy-Item "$siteJars\fabric-installer.jar" "$dest\jars\fabric-installer.jar" -Force
}

Write-Host "Building DanyaClient Release..."
dotnet build "$dest\DanyaClientLoader.csproj" -c Release

# Copy output executable directly to root of INOAGENT LOADER for convenience
$binDir = "$dest\bin\Release\net8.0-windows"
if (Test-Path "$binDir\DanyaClient.exe") {
    Copy-Item "$binDir\*" "$dest\" -Recurse -Force
    # Ensure jars are present in output folder as well
    New-Item -ItemType Directory -Force -Path "$binDir\jars" | Out-Null
    Copy-Item "$dest\jars\*" "$binDir\jars\" -Force
    Write-Host "DanyaClient.exe successfully placed in INOAGENT LOADER!"
}
