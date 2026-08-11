$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$ws = "b0e297a1-0305-4c69-92d7-e32ff2045ba9"
$model = "1adf9d89-c5b3-4b0c-81d3-8ac57bee3564"
$tok = az account get-access-token --resource "https://analysis.windows.net/powerbi/api" --query accessToken -o tsv
$headers = @{ Authorization = "Bearer $tok"; "Content-Type" = "application/json" }
$dax = @"
EVALUATE
ROW(
  "TotalCost", [TotalCost],
  "TotalRequests", [TotalRequests],
  "TotalErrors", [TotalErrors],
  "ErrorRate", [ErrorRate],
  "P90Latency", [P90Latency],
  "P99Latency", [P99Latency],
  "AvailabilityPct", [AvailabilityPct],
  "ResourceCount", [ResourceCount],
  "CostPerRequest", [CostPerRequest],
  "CapacityUtilization", [CapacityUtilization]
)
"@
$body = @{ queries = @(@{ query = $dax }); serializerSettings = @{ includeNulls = $true } } | ConvertTo-Json -Depth 6
try {
    $r = Invoke-RestMethod -UseBasicParsing -Method Post -Uri "https://api.powerbi.com/v1.0/myorg/groups/$ws/datasets/$model/executeQueries" -Headers $headers -Body $body
    $r.results[0].tables[0].rows | ConvertTo-Json -Depth 6
} catch {
    Write-Host "QUERY ERROR: $($_.Exception.Message)"
    if ($_.ErrorDetails.Message) { Write-Host $_.ErrorDetails.Message }
}
