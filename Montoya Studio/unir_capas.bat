@echo off
REM Une las 5 partes del instalador NUEVO (con renglones) de Montoya Studio y verifica que quedo identico.
cd /d "%~dp0"
copy /b "MS-capas-x64.exe.001"+"MS-capas-x64.exe.002"+"MS-capas-x64.exe.003"+"MS-capas-x64.exe.004"+"MS-capas-x64.exe.005" "Montoya-Studio-0.1.0-capas-windows-x64.exe"
echo.
echo Huella SHA256 del instalador unido:
certutil -hashfile "Montoya-Studio-0.1.0-capas-windows-x64.exe" SHA256
echo Debe coincidir con:
echo 9d95e8e94407e4cd6dc4607daf26b922d8eda97c54dfca5403f93c96ecded2c1
echo.
echo Si coincide: cierra Montoya Studio si esta abierto y abre Montoya-Studio-0.1.0-capas-windows-x64.exe para instalar.
echo Tus proyectos se conservan.
pause
