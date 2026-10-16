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
    foreach ($ambientePedidos in @('.venv', 'venv32')) {
        $pythonPedidos = Join-Path $PSScriptRoot "$ambientePedidos\Scripts\pythonw.exe"
        if (Test-Path -LiteralPath $pythonPedidos -PathType Leaf) {
            $destinoPedidos = $pythonPedidos
            break
        }
    }
    if (-not $destinoPedidos) {
        throw 'Pedidos Havan.exe e o Python de .venv ou venv32 não foram encontrados. Consulte o README.'
    }
    $argumentosPedidos = '"' + $scriptPedidos + '"'
    $recursosPedidos += $scriptPedidos
}
foreach ($recursoPedidos in $recursosPedidos) {
    if (-not (Test-Path -LiteralPath $recursoPedidos -PathType Leaf)) {
        throw "Recurso não encontrado: $recursoPedidos"
    }
}
$shellPedidos = New-Object -ComObject WScript.Shell
$atalhoPedidos = $shellPedidos.CreateShortcut((Join-Path $PSScriptRoot 'Abrir Pedidos Havan.lnk'))
$atalhoPedidos.TargetPath = $destinoPedidos
$atalhoPedidos.Arguments = $argumentosPedidos
$atalhoPedidos.WorkingDirectory = $PSScriptRoot
$atalhoPedidos.IconLocation = $iconePedidos + ',0'
$atalhoPedidos.Description = 'Inserir, retomar e reimprimir pedidos Havan'
$atalhoPedidos.WindowStyle = 1
$atalhoPedidos.Save()
Write-Output 'Atalho Pedidos Havan criado com o ícone Nunes.'
