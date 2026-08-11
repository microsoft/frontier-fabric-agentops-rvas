$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$ws = "b0e297a1-0305-4c69-92d7-e32ff2045ba9"
$root = "c:\Users\angandin\repos\Personal\RVAS\frontier-fabric-agentops-rvas\resources\fabric-control-tower\.build\AgentOpsControlTower.Report"
$fabTok = az account get-access-token --resource "https://api.fabric.microsoft.com" --query accessToken -o tsv
$headers = @{ Authorization = "Bearer $fabTok"; "Content-Type" = "application/json"; "x-ms-fabric-skill" = "powerbi-report-management" }

$files = Get-ChildItem -Path $root -Recurse -File
$parts = @()
foreach ($f in $files) {
    $rel = $f.FullName.Substring($root.Length + 1).Replace("\", "/")
    $b64 = [Convert]::ToBase64String([System.IO.File]::ReadAllBytes($f.FullName))
    $parts += [ordered]@{ path = $rel; payload = $b64; payloadType = "InlineBase64" }
}
Write-Host "parts: $($parts.Count)"
$body = [ordered]@{ displayName = "AgentOps Control Tower"; description = "Reliability / Cost / Performance report over the Direct Lake Gold model (Challenge 5)."; definition = [ordered]@{ parts = $parts } } | ConvertTo-Json -Depth 12

$resp = Invoke-WebRequest -UseBasicParsing -Method Post -Uri "https://api.fabric.microsoft.com/v1/workspaces/$ws/reports" -Headers $headers -Body $body
Write-Host "STATUS: $($resp.StatusCode)"
if ($resp.StatusCode -eq 202) {
    $opUrl = $resp.Headers["Location"]; if ($opUrl -is [array]) { $opUrl = $opUrl[0] }
    do { Start-Sleep -Seconds 3; $op = Invoke-RestMethod -Uri $opUrl -Headers @{ Authorization = "Bearer $fabTok"; "x-ms-fabric-skill" = "powerbi-report-management" }; Write-Host "  state: $($op.status)" } while ($op.status -in @("Running", "NotStarted"))
    if ($op.status -ne "Succeeded") { $op | ConvertTo-Json -Depth 10 | Write-Host; throw "report LRO failed" }
    $result = Invoke-RestMethod -Uri "$opUrl/result" -Headers @{ Authorization = "Bearer $fabTok"; "x-ms-fabric-skill" = "powerbi-report-management" }
    Write-Host "REPORT_ID: $($result.id)"
} else {
    $obj = $resp.Content | ConvertFrom-Json
    Write-Host "REPORT_ID: $($obj.id)"
}
