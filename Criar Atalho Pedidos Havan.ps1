# Recrie o atalho depois de mover a pasta da aplicação.
$ErrorActionPreference = 'Stop'
$scriptPedidos = Join-Path $PSScriptRoot 'Abrir Pedidos Havan.cmd'
$iconePedidos = Join-Path $PSScriptRoot 'icons\icone.ico'
foreach ($recursoPedidos in @($scriptPedidos, $iconePedidos)) {
    if (-not (Test-Path -LiteralPath $recursoPedidos -PathType Leaf)) {
        throw "Recurso não encontrado: $recursoPedidos"
    }
}
$shellPedidos = New-Object -ComObject WScript.Shell
$atalhoPedidos = $shellPedidos.CreateShortcut((Join-Path $PSScriptRoot 'Abrir Pedidos Havan.lnk'))
$atalhoPedidos.TargetPath = $scriptPedidos
$atalhoPedidos.WorkingDirectory = $PSScriptRoot
$atalhoPedidos.IconLocation = $iconePedidos + ',0'
$atalhoPedidos.Description = 'Inserir, retomar e reimprimir pedidos Havan'
$atalhoPedidos.WindowStyle = 7
$atalhoPedidos.Save()
Write-Output 'Atalho Pedidos Havan criado com o ícone Nunes.'
