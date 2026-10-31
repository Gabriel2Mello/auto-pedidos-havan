# Recrie o atalho depois de mover a pasta da aplicação.
$ErrorActionPreference = 'Stop'
$executavelPedidos = Join-Path $PSScriptRoot 'Pedidos Havan.exe'
$scriptPedidos = Join-Path $PSScriptRoot 'havan.py'
$iconePedidos = Join-Path $PSScriptRoot 'icons\icone.ico'
$argumentosPedidos = ''
$recursosPedidos = @($iconePedidos)
if (Test-Path -LiteralPath $executavelPedidos -PathType Leaf) {
    $destinoPedidos = $executavelPedidos
} else {
    $destinoPedidos = $null
    foreach ($ambientePedidos in @('.venv-desktop')) {
        $pythonPedidos = Join-Path $PSScriptRoot "$ambientePedidos\Scripts\pythonw.exe"
        if (Test-Path -LiteralPath $pythonPedidos -PathType Leaf) {
            $destinoPedidos = $pythonPedidos
            break
        }
    }
    if (-not $destinoPedidos) {
        throw 'Pedidos Havan.exe e o Python de .venv-desktop não foram encontrados. Consulte o README.'
    }
    $argumentosPedidos = '"' + $scriptPedidos + '"'
    $recursosPedidos += $scriptPedidos
}
foreach ($recursoPedidos in $recursosPedidos) {
    if (-not (Test-Path -LiteralPath $recursoPedidos -PathType Leaf)) {
        throw "Recurso não encontrado: $recursoPedidos"
    }
}
if ($argumentosPedidos) { & $destinoPedidos $scriptPedidos --criar-atalho (Join-Path $PSScriptRoot 'Abrir Pedidos Havan.lnk'); exit $LASTEXITCODE }
& $destinoPedidos --criar-atalho (Join-Path $PSScriptRoot 'Abrir Pedidos Havan.lnk')
if ($LASTEXITCODE -ne 0) { throw 'Não foi possível criar o atalho desktop.' }
exit 0
