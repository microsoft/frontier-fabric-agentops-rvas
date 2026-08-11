$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$ws = "b0e297a1-0305-4c69-92d7-e32ff2045ba9"
$nbId = "5b1c38c6-11df-4d2b-8d00-005b931fac3c"
$t = az account get-access-token --resource "https://api.fabric.microsoft.com" --query accessToken -o tsv
$h = @{ Authorization = "Bearer $t" }
$hj = @{ Authorization = "Bearer $t"; "Content-Type" = "application/json" }

# resolve the mirrored database id
$mdb = (Invoke-RestMethod -UseBasicParsing -Uri "https://api.fabric.microsoft.com/v1/workspaces/$ws/mirroredDatabases" -Headers $h).value | Where-Object { $_.displayName -eq 'CosmosDB-agentsdb' }
Write-Host "MirroredDB: $($mdb.displayName) = $($mdb.id)"

function Get-NbJson {
    $resp = Invoke-WebRequest -UseBasicParsing -Method Post -Uri "https://api.fabric.microsoft.com/v1/workspaces/$ws/items/$nbId/getDefinition?format=ipynb" -Headers $hj -Body '{}'
    if ($resp.StatusCode -eq 202) {
        $op = $resp.Headers["Location"]; if ($op -is [array]) { $op = $op[0] }
        do { Start-Sleep 3; $s = Invoke-RestMethod -Uri $op -Headers $h } while ($s.status -in @('Running', 'NotStarted'))
        $body = Invoke-RestMethod -Uri "$op/result" -Headers $h
    } else { $body = $resp.Content | ConvertFrom-Json }
    $part = $body.definition.parts | Where-Object { $_.path -like '*.ipynb' }
    return @{ path = $part.path; text = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($part.payload)) }
}

$nb = Get-NbJson
$obj = $nb.text | ConvertFrom-Json
$deps = $obj.metadata.dependencies

# ensure lakehouse.known_lakehouses does NOT contain the mirrored db
if ($deps.lakehouse -and $deps.lakehouse.known_lakehouses) {
    $deps.lakehouse.known_lakehouses = @($deps.lakehouse.known_lakehouses | Where-Object { $_.id -ne $mdb.id })
}
# attach the mirroring artifact under mirrored_db.known_mirrored_dbs
if (-not $deps.mirrored_db) { $deps | Add-Member -NotePropertyName mirrored_db -NotePropertyValue ([pscustomobject]@{ known_mirrored_dbs = @() }) -Force }
$existing = @($deps.mirrored_db.known_mirrored_dbs | Where-Object { $_.id -eq $mdb.id })
if ($existing.Count -eq 0) {
    $deps.mirrored_db.known_mirrored_dbs = @($deps.mirrored_db.known_mirrored_dbs + ([pscustomobject]@{ id = $mdb.id }))
}

$newText = $obj | ConvertTo-Json -Depth 40
$enc = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($newText))
$body = @{ definition = @{ format = "ipynb"; parts = @(@{ path = $nb.path; payload = $enc; payloadType = "InlineBase64" }) } } | ConvertTo-Json -Depth 10
$resp = Invoke-WebRequest -UseBasicParsing -Method Post -Uri "https://api.fabric.microsoft.com/v1/workspaces/$ws/items/$nbId/updateDefinition" -Headers $hj -Body $body
if ($resp.StatusCode -eq 202) { $op = $resp.Headers["Location"]; if ($op -is [array]) { $op = $op[0] }; do { Start-Sleep 3; $s = Invoke-RestMethod -Uri $op -Headers $h } while ($s.status -in @('Running', 'NotStarted')); Write-Host "update: $($s.status)" } else { Write-Host "update: $($resp.StatusCode)" }

Start-Sleep 3
$after = Get-NbJson
Write-Host "== dependencies after =="
($after.text | ConvertFrom-Json).metadata.dependencies | ConvertTo-Json -Depth 8
