$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$ws = "b0e297a1-0305-4c69-92d7-e32ff2045ba9"
$model = "1adf9d89-c5b3-4b0c-81d3-8ac57bee3564"
$root = "c:\Users\angandin\repos\Personal\RVAS\frontier-fabric-agentops-rvas\resources\fabric-control-tower\.build\ObservabilityAnalytics.SemanticModel"
$fabTok = az account get-access-token --resource "https://api.fabric.microsoft.com" --query accessToken -o tsv
$headers = @{ Authorization = "Bearer $fabTok"; "Content-Type" = "application/json"; "x-ms-fabric-skill" = "semantic-model-authoring" }

$files = Get-ChildItem -Path $root -Recurse -File | Where-Object { $_.Name -ne ".platform" }
$parts = @()
foreach ($f in $files) {
    $rel = $f.FullName.Substring($root.Length + 1).Replace("\", "/")
    $b64 = [Convert]::ToBase64String([System.IO.File]::ReadAllBytes($f.FullName))
    $parts += [ordered]@{ path = $rel; payload = $b64; payloadType = "InlineBase64" }
}
$body = [ordered]@{ definition = [ordered]@{ format = "TMDL"; parts = $parts } } | ConvertTo-Json -Depth 10

Write-Host "== updateDefinition =="
$resp = Invoke-WebRequest -UseBasicParsing -Method Post -Uri "https://api.fabric.microsoft.com/v1/workspaces/$ws/semanticModels/$model/updateDefinition" -Headers $headers -Body $body
Write-Host "STATUS: $($resp.StatusCode)"
if ($resp.StatusCode -eq 202) {
    $opUrl = $resp.Headers["Location"]; if ($opUrl -is [array]) { $opUrl = $opUrl[0] }
    do { Start-Sleep -Seconds 3; $op = Invoke-RestMethod -Uri $opUrl -Headers @{ Authorization = "Bearer $fabTok"; "x-ms-fabric-skill" = "semantic-model-authoring" }; Write-Host "  state: $($op.status)" } while ($op.status -in @("Running", "NotStarted"))
    if ($op.status -ne "Succeeded") { $op | ConvertTo-Json -Depth 8 | Write-Host; throw "update failed" }
}

Write-Host "== bind connection (Automatic SSO) =="
$bind = @{ connectionBinding = @{ connectivityType = "Automatic"; connectionDetails = @{ type = "Sql"; path = "7x56ffa4c6ge7g3q7puaalnmla-ugl6fmafanuuzewx4mx7ebc3ve.datawarehouse.fabric.microsoft.com;Observability" } } } | ConvertTo-Json -Depth 6
try {
    Invoke-RestMethod -UseBasicParsing -Method Post -Uri "https://api.fabric.microsoft.com/v1/workspaces/$ws/semanticModels/$model/bindConnection" -Headers $headers -Body $bind
    Write-Host "bound"
} catch { $sr = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream()); Write-Host ("bind: " + $sr.ReadToEnd()) }

Write-Host "== current connections =="
(Invoke-RestMethod -UseBasicParsing -Uri "https://api.fabric.microsoft.com/v1/workspaces/$ws/items/$model/connections" -Headers $headers).value | ConvertTo-Json -Depth 6
