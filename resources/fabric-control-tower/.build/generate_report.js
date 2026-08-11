const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const OUT = path.join(__dirname, 'AgentOpsControlTower.Report');
const MODEL_ID = '1adf9d89-c5b3-4b0c-81d3-8ac57bee3564';
const WS_NAME = 'ws_sc_fct';
const MODEL_NAME = 'Observability Analytics';
const BASETHEME_SRC = 'C:\\Users\\angandin\\.copilot\\repos\\gelatai-factory\\Fabric\\ws_wu3_gelatai\\rp_gelatai_lh.Report\\StaticResources\\SharedResources\\BaseThemes\\CY26SU05.json';

const S_VIS = 'https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.10.0/schema.json';
const S_PAGE = 'https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json';

// ---- design system (matched to the gelatai chargeback report) ----
const HEADER_BG = '#2D2A5A';   // dark indigo header band
const HEADER_SUB = '#C9D1E8';  // header subtitle
const WALL = '#F4F5FA';        // page canvas
const CARD = '#FFFFFF';
const BORDER = '#E3E6EF';
const TITLE_MUTE = '#5B6474';  // muted H6 visual titles
const VALUE = '#4C51BF';       // KPI value indigo
const SERIES = ['#4C51BF', '#4C9AFF', '#36B37E', '#FFAB00', '#6554C0', '#00B8D9'];
const RED = '#FF5630';

const rid = () => crypto.randomBytes(10).toString('hex');

// literal helpers
const L = v => ({ expr: { Literal: { Value: v } } });
const Lb = b => L(b ? 'true' : 'false');
const Ls = s => L(`'${s}'`);
const Ld = n => L(`${n}D`);
const solid = c => ({ solid: { color: Ls(c) } });

// field expressions
const measure = (t, p) => ({ Measure: { Expression: { SourceRef: { Entity: t } }, Property: p } });
const column = (t, p) => ({ Column: { Expression: { SourceRef: { Entity: t } }, Property: p } });
const pM = (t, p) => ({ field: measure(t, p), queryRef: `${t}.${p}`, nativeQueryRef: p });
const pC = (t, p) => ({ field: column(t, p), queryRef: `${t}.${p}`, nativeQueryRef: p, active: true });

const container = (pos, visual) => ({ $schema: S_VIS, name: rid(), position: { x: pos[0], y: pos[1], z: pos[4], height: pos[3], width: pos[2], tabOrder: pos[4] }, visual });

// shared chrome + muted H6 title
function chrome(title) {
  const o = {
    background: [{ properties: { show: Lb(true), color: solid(CARD) } }],
    border: [{ properties: { show: Lb(true), color: solid(BORDER), radius: Ld(12) } }],
    dropShadow: [{ properties: { show: Lb(true) } }]
  };
  if (title) o.title = [{ properties: { show: Lb(true), text: Ls(title), fontColor: solid(TITLE_MUTE), heading: Ls('H6') } }];
  return o;
}

// ---- header band ----
function header(title, subtitle) {
  return container([0, 0, 1280, 64, 0], {
    visualType: 'textbox',
    objects: { general: [{ properties: { paragraphs: [
      { horizontalTextAlignment: 'left', textRuns: [{ value: title, textStyle: { fontSize: '22px', fontWeight: '700', color: '#FFFFFF', fontFamily: 'Segoe UI Semibold' } }] },
      { horizontalTextAlignment: 'left', textRuns: [{ value: subtitle, textStyle: { fontSize: '12px', color: HEADER_SUB } }] }
    ] } }] },
    visualContainerObjects: {
      background: [{ properties: { show: Lb(true), color: solid(HEADER_BG) } }],
      padding: [{ properties: { left: Ld(24), top: Ld(10) } }]
    }
  });
}

// ---- data visuals ----
function kpi(pos, t, p, title) {
  return container(pos, {
    visualType: 'card',
    query: { queryState: { Values: { projections: [pM(t, p)] } } },
    objects: {
      labels: [{ properties: { color: solid(VALUE), fontSize: Ld(26), bold: Lb(true) } }],
      categoryLabels: [{ properties: { show: Lb(false) } }]
    },
    visualContainerObjects: chrome(title)
  });
}
function multiCard(pos, projections, title) {
  return container(pos, {
    visualType: 'multiRowCard',
    query: { queryState: { Values: { projections } } },
    visualContainerObjects: chrome(title)
  });
}
function fills(yProjs) {
  return yProjs.map((pr, i) => {
    const isErr = /error/i.test(pr.nativeQueryRef);
    return { properties: { fill: solid(isErr ? RED : SERIES[i % SERIES.length]) }, selector: { metadata: pr.queryRef } };
  });
}
function chart(type, pos, catProj, yProjs, title, sortMeasure) {
  const query = { queryState: { Category: { projections: [catProj] }, Y: { projections: yProjs } } };
  if (sortMeasure) query.sortDefinition = { sort: [{ field: measure(sortMeasure[0], sortMeasure[1]), direction: 'Descending' }], isDefaultSort: false };
  return container(pos, { visualType: type, query, objects: { dataPoint: fills(yProjs) }, visualContainerObjects: chrome(title) });
}
function tableViz(pos, projections, title) {
  return container(pos, { visualType: 'tableEx', query: { queryState: { Values: { projections } } }, visualContainerObjects: chrome(title) });
}
function slicer(pos, t, col, label) {
  return container(pos, {
    visualType: 'slicer',
    query: { queryState: { Values: { projections: [pC(t, col)] } } },
    objects: {
      data: [{ properties: { mode: Ls('Basic') } }],
      selection: [{ properties: { selectAllCheckboxEnabled: Lb(true), singleSelect: Lb(false) } }],
      header: [{ properties: { show: Lb(false) } }],
      items: [{ properties: { fontColor: solid('#2B2B40'), fontSize: Ld(10) } }]
    },
    visualContainerObjects: chrome(label)
  });
}

// ---- pages ----
const pages = [];
function page(display, visuals) { const name = rid(); pages.push({ name, display, visuals }); return name; }

// Page 0 - Overview
page('Overview', [
  header('AI AgentOps Control Tower', 'Executive overview — reliability, cost & performance across the agent estate   ·   Direct Lake · Gold layer · ws_sc_fct'),
  slicer([16, 76, 232, 170, 1], 'Calendar', 'Month', 'Month'),
  slicer([16, 258, 232, 170, 2], 'OperationalMetrics', 'service_name', 'Service'),
  slicer([16, 440, 232, 170, 3], 'AgentAnalytics', 'topic_classification', 'Topic'),
  kpi([264, 76, 156, 96, 10], 'CostSummary', 'TotalCost', 'Total cost'),
  kpi([432, 76, 156, 96, 11], 'CostSummary', 'CostMoM %', 'Cost MoM %'),
  kpi([600, 76, 156, 96, 12], 'OperationalMetrics', 'ErrorRate', 'Error rate'),
  kpi([768, 76, 156, 96, 13], 'OperationalMetrics', 'P95Latency', 'P95 latency (ms)'),
  kpi([936, 76, 156, 96, 14], 'AgentAnalytics', 'ConversationCount', 'Conversations'),
  kpi([1104, 76, 160, 96, 15], 'OperationalMetrics', 'TotalRequests', 'Requests'),
  chart('lineChart', [264, 182, 484, 256, 20], pC('OperationalMetrics', 'metric_date'), [pM('OperationalMetrics', 'P90Latency'), pM('OperationalMetrics', 'P95Latency'), pM('OperationalMetrics', 'P99Latency')], 'Latency percentiles (ms)'),
  chart('columnChart', [760, 182, 504, 256, 21], pC('Calendar', 'Month'), [pM('CostSummary', 'TotalCost')], 'Monthly Fabric spend'),
  chart('clusteredColumnChart', [264, 446, 484, 258, 22], pC('OperationalMetrics', 'service_name'), [pM('OperationalMetrics', 'TotalRequests'), pM('OperationalMetrics', 'TotalErrors')], 'Traffic & errors by service'),
  chart('barChart', [760, 446, 504, 258, 23], pC('AgentAnalytics', 'topic_classification'), [pM('AgentAnalytics', 'InteractionCount')], 'Interactions by topic', ['AgentAnalytics', 'InteractionCount'])
]);

// Page 1 - Reliability
page('Reliability', [
  header('Reliability', 'Which agents are healthy?  Error rate, latency percentiles and availability by service   ·   ws_sc_fct'),
  slicer([16, 76, 232, 264, 1], 'OperationalMetrics', 'service_name', 'Service'),
  slicer([16, 352, 232, 264, 2], 'Calendar', 'Month', 'Month'),
  kpi([264, 76, 232, 96, 10], 'OperationalMetrics', 'ErrorRate', 'Error rate'),
  kpi([510, 76, 232, 96, 11], 'OperationalMetrics', 'P95Latency', 'P95 latency (ms)'),
  kpi([756, 76, 232, 96, 12], 'OperationalMetrics', 'P99Latency', 'P99 latency (ms)'),
  kpi([1002, 76, 262, 96, 13], 'OperationalMetrics', 'AvailabilityPct', 'Availability'),
  chart('lineChart', [264, 182, 484, 256, 20], pC('OperationalMetrics', 'metric_date'), [pM('OperationalMetrics', 'P90Latency'), pM('OperationalMetrics', 'P95Latency'), pM('OperationalMetrics', 'P99Latency')], 'Latency percentile trend (ms)'),
  chart('clusteredColumnChart', [760, 182, 504, 256, 21], pC('OperationalMetrics', 'service_name'), [pM('OperationalMetrics', 'TotalRequests'), pM('OperationalMetrics', 'TotalErrors')], 'Requests vs errors by service'),
  chart('lineChart', [264, 446, 484, 258, 22], pC('OperationalMetrics', 'metric_date'), [pM('OperationalMetrics', 'AvailabilityPct')], 'Availability % trend'),
  tableViz([760, 446, 504, 258, 23], [pC('OperationalMetrics', 'service_name'), pM('OperationalMetrics', 'TotalRequests'), pM('OperationalMetrics', 'TotalErrors'), pM('OperationalMetrics', 'ErrorRate'), pM('OperationalMetrics', 'P99Latency'), pM('OperationalMetrics', 'AvailabilityPct')], 'Service health detail')
]);

// Page 2 - Cost
page('Cost', [
  header('Cost', 'What is each service & capacity costing?  Fabric spend, month-over-month trend and estate compliance   ·   ws_sc_fct'),
  slicer([16, 76, 232, 264, 1], 'Calendar', 'Month', 'Month'),
  slicer([16, 352, 232, 264, 2], 'ResourceInventory', 'resource_type', 'Resource Type'),
  kpi([264, 76, 232, 96, 10], 'CostSummary', 'TotalCost', 'Total cost'),
  kpi([510, 76, 232, 96, 11], 'CostSummary', 'CostMoM %', 'Cost MoM %'),
  kpi([756, 76, 232, 96, 12], 'CostSummary', 'CostYTD', 'Cost YTD'),
  kpi([1002, 76, 262, 96, 13], 'CostSummary', 'CostPerRequest', 'Cost / request'),
  chart('columnChart', [264, 182, 484, 256, 20], pC('Calendar', 'Month'), [pM('CostSummary', 'TotalCost')], 'Spend by month'),
  chart('barChart', [760, 182, 504, 256, 21], pC('ResourceInventory', 'resource_type'), [pM('ResourceInventory', 'TotalResourceCost')], 'Cost by resource type', ['ResourceInventory', 'TotalResourceCost']),
  tableViz([264, 446, 652, 258, 22], [pC('ResourceInventory', 'resource_name'), pC('ResourceInventory', 'resource_type'), pC('ResourceInventory', 'region'), pM('ResourceInventory', 'TotalResourceCost'), pM('ResourceInventory', 'CompliancePct')], 'Resource cost & compliance'),
  multiCard([932, 446, 332, 258, 23], [pM('ResourceInventory', 'ResourceCount'), pM('ResourceInventory', 'TotalResourceCost'), pM('ResourceInventory', 'CompliancePct')], 'Estate summary')
]);

// Page 3 - Performance
page('Performance', [
  header('Performance', 'Are we meeting SLAs & scaling?  Conversation volume, topic mix and token consumption   ·   ws_sc_fct'),
  slicer([16, 76, 232, 264, 1], 'Calendar', 'Month', 'Month'),
  slicer([16, 352, 232, 264, 2], 'AgentAnalytics', 'topic_classification', 'Topic'),
  kpi([264, 76, 232, 96, 10], 'AgentAnalytics', 'ConversationCount', 'Conversations'),
  kpi([510, 76, 232, 96, 11], 'AgentAnalytics', 'InteractionCount', 'Interactions'),
  kpi([756, 76, 232, 96, 12], 'OperationalMetrics', 'TotalRequests', 'Requests'),
  kpi([1002, 76, 262, 96, 13], 'CapacityUsage', 'CapacityUtilization', 'Avg capacity metric'),
  chart('lineChart', [264, 182, 484, 256, 20], pC('AgentAnalytics', 'interaction_date'), [pM('AgentAnalytics', 'ConversationCount'), pM('AgentAnalytics', 'InteractionCount')], 'Conversation & interaction volume'),
  chart('clusteredColumnChart', [760, 182, 504, 256, 21], pC('AgentAnalytics', 'topic_classification'), [pM('AgentAnalytics', 'InteractionCount')], 'Interactions by topic', ['AgentAnalytics', 'InteractionCount']),
  chart('clusteredColumnChart', [264, 446, 484, 258, 22], pC('CapacityUsage', 'metric_name'), [pM('CapacityUsage', 'AvgMetricValue'), pM('CapacityUsage', 'MaxMetricValue')], 'Agent token & execution metrics'),
  tableViz([760, 446, 504, 258, 23], [pC('AgentAnalytics', 'topic_classification'), pM('AgentAnalytics', 'ConversationCount'), pM('AgentAnalytics', 'InteractionCount'), pM('AgentAnalytics', 'AvgMessageLength')], 'Topic engagement detail')
]);

// ---- write files ----
function w(p, obj) { fs.mkdirSync(path.dirname(p), { recursive: true }); fs.writeFileSync(p, typeof obj === 'string' ? obj : JSON.stringify(obj, null, 2)); }

if (fs.existsSync(OUT)) fs.rmSync(OUT, { recursive: true, force: true });

w(path.join(OUT, '.platform'), { $schema: 'https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json', metadata: { type: 'Report', displayName: 'AgentOps Control Tower' }, config: { version: '2.0', logicalId: '00000000-0000-0000-0000-000000000000' } });

w(path.join(OUT, 'definition.pbir'), {
  $schema: 'https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json',
  version: '4.0',
  datasetReference: { byConnection: { connectionString: `Data Source=powerbi://api.powerbi.com/v1.0/myorg/${WS_NAME};initial catalog=${MODEL_NAME};integrated security=ClaimsToken;semanticmodelid=${MODEL_ID}` } }
});

w(path.join(OUT, 'definition', 'version.json'), { $schema: 'https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json', version: '2.0.0' });

w(path.join(OUT, 'definition', 'report.json'), {
  $schema: 'https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/3.3.0/schema.json',
  themeCollection: { baseTheme: { name: 'CY26SU05', reportVersionAtImport: { visual: '2.9.0', report: '3.3.0', page: '2.3.1' }, type: 'SharedResources' } },
  objects: {
    section: [{ properties: { verticalAlignment: Ls('Top') } }],
    outspacePane: [{ properties: { expanded: Lb(false) } }]
  },
  resourcePackages: [{ name: 'SharedResources', type: 'SharedResources', items: [{ name: 'CY26SU05', path: 'BaseThemes/CY26SU05.json', type: 'BaseTheme' }] }],
  settings: { useStylableVisualContainerHeader: true, exportDataMode: 'AllowSummarized', defaultDrillFilterOtherVisuals: true, allowChangeFilterTypes: true, useEnhancedTooltips: true }
});

fs.mkdirSync(path.join(OUT, 'StaticResources', 'SharedResources', 'BaseThemes'), { recursive: true });
fs.copyFileSync(BASETHEME_SRC, path.join(OUT, 'StaticResources', 'SharedResources', 'BaseThemes', 'CY26SU05.json'));

w(path.join(OUT, 'definition', 'pages', 'pages.json'), { $schema: 'https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.1.0/schema.json', pageOrder: pages.map(p => p.name), activePageName: pages[0].name });

const pageObjects = { background: [{ properties: { color: solid(WALL), transparency: Ld(0) } }] };

for (const pg of pages) {
  const pdir = path.join(OUT, 'definition', 'pages', pg.name);
  w(path.join(pdir, 'page.json'), { $schema: S_PAGE, name: pg.name, displayName: pg.display, displayOption: 'FitToPage', height: 720, width: 1280, objects: pageObjects });
  for (const v of pg.visuals) { w(path.join(pdir, 'visuals', v.name, 'visual.json'), v); }
}

console.log('Report generated at', OUT);
console.log('Pages:', pages.map(p => `${p.display} (${p.visuals.length} visuals)`).join(', '));
