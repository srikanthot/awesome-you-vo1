function ExecuteScript() {
  /*
   * Alessa extraction for Power Automate Desktop – "Run JavaScript function on web page".
   * Run it on the signed-in Alessa tab (the Entity 360 work items page).
   * READ-ONLY: only the read calls listed in ALLOWED are sent. It returns a JSON string with
   * one case package per work item (same shape as the Python extractor, minus accounts/profile).
   * PAD replaces %MaxItems% and %LookbackDays% with flow variables before running it.
   * Synchronous XHR is used on purpose: PAD's JavaScript action does not wait for promises.
   */
  var MAX_ITEMS = parseInt('%MaxItems%', 10) || 3;
  var LOOKBACK_DAYS = parseInt('%LookbackDays%', 10) || 365;
  var STATES = ['Assigned'];          // _Monitor_WorkflowStateName values to include
  var MODULES = ['TM Alerts'];        // MODULES_UPDATED values to include
  var RS = { id: parseInt('%ResultSetId%', 10), process: parseInt('%ProcessId%', 10), typeId: 11, resolution: 1, wiType: 2, table: '%ResultSetTable%' };
  var B = '/ResultsManagement', E = B + '/EntityThreeSixty';
  var ALLOWED = [B + '/GridView/GetResultSetPage', E + '/GetEntityThreeSixtyResultSetInitialInformation',
    E + '/GetPagedEntityThreeSixtyTransMonAlerts', E + '/GetEntityThreeSixtyTransMonAlertDetails',
    E + '/GetPagedEntityThreeSixtyTransactions'];

  function call(method, path, params, body) {
    if (ALLOWED.indexOf(path) < 0) throw new Error('blocked: ' + path);
    var q = { _dc: Date.now(), action: 'read', start: 0, page: 1, PageIndex: 1, Start: 0 };
    for (var k in params) q[k] = params[k];
    var url = path + (method === 'GET' ? '?' + Object.keys(q).map(function (k) {
      return encodeURIComponent(k) + '=' + encodeURIComponent(q[k]);
    }).join('&') : '');
    var x = new XMLHttpRequest();
    x.open(method, url, false);
    if (method === 'POST') x.setRequestHeader('Content-Type', 'application/json');
    x.send(method === 'POST' ? JSON.stringify(body) : null);
    var ct = x.getResponseHeader('content-type') || '';
    if (x.status !== 200 || ct.indexOf('json') < 0) throw new Error('session expired or error on ' + path + ' (HTTP ' + x.status + ')');
    return JSON.parse(x.responseText);
  }
  function sort(p) { return JSON.stringify([{ property: p, direction: 'DESC' }]); }
  function paged(path, key, params, sortBy) {
    var out = [], size = 1000;
    for (var page = 1; page <= 50; page++) {
      var p = { PageSize: size, page: page, PageIndex: page, start: (page - 1) * size, Start: (page - 1) * size, Sort: sort(sortBy) };
      for (var k in params) p[k] = params[k];
      var d = (call('GET', path, p).data) || {};
      var rows = d[key] || [];
      out = out.concat(rows);
      if (rows.length < size || out.length >= (d.TotalRecords || 0)) break;
    }
    return out;
  }
  function day(d) { return d.toISOString().slice(0, 10) + 'T00:00:00'; }

  // 1. pick work items from Entity 360 Master
  var picked = [];
  for (var pg = 1; pg <= 50 && picked.length < MAX_ITEMS; pg++) {
    var rows = call('GET', B + '/GridView/GetResultSetPage', {
      ResultSetId: RS.id, ProcessId: RS.process, WorkItemTypeId: RS.typeId, ResolutionType: RS.resolution,
      WorkItemType: RS.wiType, ResultSetTableName: RS.table, RiskId: -1, TimePeriodId: 0, WorkflowId: -1,
      WorkflowStateId: -1, page: pg, PageIndex: pg, start: (pg - 1) * 100, Start: (pg - 1) * 100, PageSize: 100, limit: 100,
      Sort: sort('_Monitor_WorkItemID')
    }).data || [];
    rows.forEach(function (r) {
      if (STATES.indexOf(r._Monitor_WorkflowStateName) >= 0 && MODULES.indexOf(r.MODULES_UPDATED) >= 0 && picked.length < MAX_ITEMS) picked.push(r);
    });
    if (rows.length < 100) break;
  }

  // 2. build a case package per work item
  var end = new Date(Date.now() + 86400000), start = new Date(end.getTime() - LOOKBACK_DAYS * 86400000);
  var cases = picked.map(function (r) {
    var t0 = Date.now(), wid = r._Monitor_WorkItemID, aid = r.ALESSA_ID, eid = r.ENTITY_ID || aid, warnings = [];
    var body = { WorkitemPropertyId: 0, RiskId: -1, TimePeriodId: 0, WorkflowStateId: -1, IndicatorId: 0, IndicatorValue: null,
      UserId: 0, WorkItemTypeId: RS.typeId, ResultSetId: String(RS.id), WorkflowId: -1, ResolutionType: RS.resolution,
      WorkItemType: RS.wiType, StartDate: '0001-01-01T00:00:00', EndDate: '0001-01-01T00:00:00', PrincipalId: 0,
      ProcessId: String(RS.process), DatabaseDateType: 0, EntityId: 0, IncludeChildrenInCount: false, ObjectId: 0,
      ObjectTypeId: 0, RunDateId: 0, WorkItemTotalsProperty: 0, WorkItems: [wid], WorkItemId: wid, PageIndex: 1,
      PageSize: 1, IsGeneric: false, FilterCondition: null, GenericFilterColumns: null, IsEntityThreeSixty: true };
    var model = ((call('POST', E + '/GetEntityThreeSixtyResultSetInitialInformation', {}, body).result) || {}).model || {};
    var txns = paged(E + '/GetPagedEntityThreeSixtyTransactions', 'Transactions', { alessaId: aid, entityId: eid,
      transactionStartDate: day(start), transactionEndDate: day(end), searchText: '', accountId: '', accountType: '' }, 'transaction_datetime');
    var byId = {}; txns.forEach(function (t) { byId[t.TransactionId] = t; });
    var alerts = paged(E + '/GetPagedEntityThreeSixtyTransMonAlerts', 'TransMonAlerts', { alessaId: aid, entityId: eid,
      alertType: 'All', searchText: '' }, 'run_date').map(function (a) {
      var trig = paged(E + '/GetEntityThreeSixtyTransMonAlertDetails', 'TransMonAlertDetails', { alessaId: aid, alertId: a.AlertId }, 'transaction_datetime')
        .map(function (t) { if (!byId[t.TransactionId]) warnings.push('alert transaction ' + t.TransactionId + ' outside window'); return byId[t.TransactionId] || t; });
      return { alert_id: a.AlertId, rule_pattern: a.RulePattern, rule_name: a.RuleName, description: a.Description,
        priority: a.Priority, run_date: a.RunDate, resolution: a.Resolution, alert_type: a.AlertType, report_id: a.ReportId,
        work_item_id: a.WorkItemId, triggering_transactions: trig };
    });
    return {
      work_item: { work_item_id: wid, state: r._Monitor_WorkflowStateName, assigned_to: r._Monitor_AssignTo,
        date_assigned: r._Monitor_DateAssigned, priority: r.PRIORITY, has_comments: r._Monitor_HasComments },
      entity: { alessa_id: aid, entity_id: eid, name: r.NAME, business_relationship: r.BUSINESS_RELATIONSHIP,
        occupation: r.OCCUPATION, country: r.COUNTRY, risk_score: r.RISK_SCORE, risk_flag: r.RISK_FLAG },
      alerts: alerts,
      transactions: txns,
      history: (model.ActionsTakenModels || []).map(function (h) {
        return { date: h.DatePerformed, performed_by: h.PerformedByText, action: h.ActionDetails, comment: h.CommentText || null };
      }),
      meta: { source: 'Alessa data calls via Power Automate (read-only)', transaction_window: [day(start), day(end)],
        warnings: warnings, seconds: (Date.now() - t0) / 1000, pii: 'UNMASKED - mask before any AI call' }
    };
  });
  return JSON.stringify({ extracted_at: new Date().toISOString(), count: cases.length, cases: cases });
}
