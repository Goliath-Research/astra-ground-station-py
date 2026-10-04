const TOKEN_KEY = "astra.web.token";

const ICONS = {
  1: "Vehicle",
  2: "Stage",
  3: "Version",
  4: "Release",
  5: "Smart node",
  6: "L2R",
  7: "R2L",
};

const state = {
  tree: [],
  selectedId: null,
  packet: null,
  fieldId: null,
  deviceId: null,
  serverId: null,
  testId: null,
  logPacketId: null,
  logOffset: 0,
};

function $(id) {
  const node = document.getElementById(id);
  if (!node) {
    throw new Error("missing " + id);
  }
  return node;
}

function text(id, value) {
  $(id).textContent = value == null || value === "" ? "—" : String(value);
}

function setStatus(message, isError) {
  const node = $("status");
  node.textContent = message || "";
  node.classList.toggle("error", Boolean(isError));
}

async function api(path, options) {
  const settings = options || {};
  const headers = new Headers();
  const token = sessionStorage.getItem(TOKEN_KEY);
  if (token) {
    headers.set("Authorization", "Bearer " + token);
  }
  let body;
  if (settings.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(settings.json);
  }
  const response = await fetch(path, {
    method: settings.method || "GET",
    headers,
    body,
  });
  if (response.status === 204) {
    return null;
  }
  const raw = await response.text();
  let payload = null;
  if (raw) {
    payload = JSON.parse(raw);
  }
  if (!response.ok) {
    const detail = payload && payload.detail ? String(payload.detail) : "request failed";
    const error = new Error(detail);
    error.status = response.status;
    throw error;
  }
  return payload;
}

function selectedNode() {
  return state.tree.find((row) => row.id === state.selectedId) || null;
}

function childrenOf(parentId) {
  return state.tree.filter((row) => row.parent_id === parentId);
}

function siblingIndex(node) {
  const siblings = childrenOf(node.parent_id);
  return siblings.findIndex((row) => row.id === node.id);
}

function renderTree() {
  const root = $("tree");
  root.replaceChildren();
  const walk = (parentId, depth) => {
    for (const row of childrenOf(parentId)) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "node";
      button.style.paddingLeft = 0.4 + depth * 0.9 + "rem";
      button.textContent = (ICONS[row.icon_id] || "Node") + ": " + row.name;
      button.setAttribute("data-node-id", String(row.id));
      if (row.id === state.selectedId) {
        button.setAttribute("aria-current", "true");
      }
      button.addEventListener("click", () => selectNode(row.id));
      root.appendChild(button);
      walk(row.id, depth + 1);
    }
  };
  walk(null, 0);
}

async function reloadTree() {
  state.tree = await api("/api/tree");
  if (state.selectedId !== null && !selectedNode()) {
    state.selectedId = null;
  }
  renderTree();
}

async function selectNode(nodeId) {
  state.selectedId = nodeId;
  clearFieldForm();
  renderTree();
  const node = selectedNode();
  if (node) {
    $("node-name").value = node.name;
    if (node.icon_id === 5) {
      $("device-smart-node").value = String(node.id);
    }
  }
  const tab = document.querySelector(".tab[aria-selected='true']");
  const name = tab ? tab.getAttribute("data-tab") : "packet";
  await showTab(name || "packet");
}

async function showTab(name) {
  for (const button of document.querySelectorAll(".tab")) {
    button.setAttribute("aria-selected", button.getAttribute("data-tab") === name ? "true" : "false");
  }
  for (const panel of document.querySelectorAll("[data-panel]")) {
    panel.hidden = panel.getAttribute("data-panel") !== name;
  }
  if (name === "packet" || name === "fields") {
    await loadPacket();
  }
  if (name === "fields") {
    await loadFields();
  } else if (name === "mappings") {
    await loadMappings();
  } else if (name === "transformations") {
    await loadTransformations();
  } else if (name === "devices") {
    await loadDevices();
  } else if (name === "servers") {
    await loadServers();
  } else if (name === "stream") {
    await loadStream();
  } else if (name === "tests") {
    await loadTests();
  }
}

function clearPacketForm() {
  state.packet = null;
  $("packet-id").value = "";
  $("packet-name").value = "";
  $("packet-is-input").checked = false;
  text("enc-size", null);
  text("dec-size", null);
}

async function loadPacket() {
  const node = selectedNode();
  $("packet-node").textContent = node
    ? (ICONS[node.icon_id] || "Node") + ": " + node.name
    : "Select a node in the tree.";
  if (!node) {
    clearPacketForm();
    return;
  }
  try {
    const packet = await api("/api/nodes/" + node.id + "/packet");
    state.packet = packet;
    $("packet-id").value = String(packet.packet_id);
    $("packet-name").value = packet.name || "";
    $("packet-is-input").checked = Boolean(packet.is_input);
    text("enc-size", packet.enc_size);
    text("dec-size", packet.dec_size);
  } catch (error) {
    clearPacketForm();
    if (error.status !== 404) {
      setStatus(error.message, true);
    }
  }
}

function addCell(row, value) {
  const cell = document.createElement("td");
  cell.textContent = value == null ? "" : String(value);
  row.appendChild(cell);
  return cell;
}

function addHeader(row, label) {
  const cell = document.createElement("th");
  cell.textContent = label;
  row.appendChild(cell);
}

async function loadFields() {
  const host = $("fields");
  host.replaceChildren();
  if (!state.packet) {
    host.textContent = "Save a packet on the selected node before editing fields.";
    return;
  }
  const types = await api("/api/scopes/" + state.selectedId + "/vartypes");
  const seen = new Set();
  const records = [];
  for (const row of types) {
    if (row.scope_id !== state.selectedId || seen.has(row.id)) {
      continue;
    }
    seen.add(row.id);
    records.push(row);
  }
  const fields = [];
  for (const record of records) {
    const rows = await api("/api/vartypes/" + record.id + "/fields");
    for (const field of rows) {
      fields.push(Object.assign({ record_name: record.name }, field));
    }
  }
  const table = document.createElement("table");
  const head = document.createElement("tr");
  for (const label of ["Record", "Name", "Type", "Qty", "Seq", "Override", "Pin"]) {
    addHeader(head, label);
  }
  table.appendChild(head);
  for (const field of fields) {
    const row = document.createElement("tr");
    addCell(row, field.record_name);
    addCell(row, field.name);
    addCell(row, field.type_name + " (" + field.type_id + ")");
    addCell(row, field.qty);
    addCell(row, field.seq);
    addCell(row, field.override ? "yes" : "no");
    addCell(row, field.connection_id);
    row.addEventListener("click", () => {
      state.fieldId = field.id;
      $("field-name").value = field.name || "";
      $("field-type-id").value = String(field.type_id);
      $("field-qty").value = String(field.qty || 1);
      $("field-seq").value = field.seq == null ? "" : String(field.seq);
      $("field-override").checked = Boolean(field.override);
    });
    table.appendChild(row);
  }
  host.appendChild(table);
}

async function loadMappings() {
  const host = $("mappings");
  host.replaceChildren();
  if (state.selectedId === null) {
    host.textContent = "Select a packet node.";
    return;
  }
  const rows = await api("/api/nodes/" + state.selectedId + "/mappings");
  if (rows.length === 0) {
    const empty = document.createElement("p");
    empty.textContent = "No ordered mappings for this node.";
    host.appendChild(empty);
    return;
  }
  const table = document.createElement("table");
  const head = document.createElement("tr");
  for (const label of ["Area", "Board", "Pin", "Field", "Record"]) {
    addHeader(head, label);
  }
  addHeader(head, "");
  table.appendChild(head);
  for (const row of rows) {
    const line = document.createElement("tr");
    addCell(line, row.area);
    addCell(line, row.board);
    addCell(line, row.first_pin);
    addCell(line, row.field);
    addCell(line, row.record);
    const action = document.createElement("td");
    const unlink = document.createElement("button");
    unlink.type = "button";
    unlink.textContent = "Unlink";
    unlink.addEventListener("click", async () => {
      try {
        await unlinkMapping(row.field_id);
      } catch (error) {
        setStatus(error.message, true);
      }
    });
    action.appendChild(unlink);
    line.appendChild(action);
    table.appendChild(line);
  }
  host.appendChild(table);
}

async function unlinkMapping(fieldId) {
  await api("/api/mappings/" + fieldId, { method: "DELETE" });
  await loadMappings();
  setStatus("Mapping cleared.", false);
}

async function linkMapping() {
  if (state.fieldId === null) {
    setStatus("Select a field on the Fields tab first.", true);
    return;
  }
  const connectionId = Number($("mapping-connection").value);
  if (!Number.isInteger(connectionId) || connectionId < 1) {
    setStatus("Enter a connection id.", true);
    return;
  }
  await api("/api/mappings", {
    method: "POST",
    json: { field_id: state.fieldId, connection_id: connectionId },
  });
  $("mapping-connection").value = "";
  await loadMappings();
  setStatus("Field linked.", false);
}

async function loadTransformations() {
  const rows = await api("/api/transformations");
  const host = $("transformations");
  host.replaceChildren();
  const table = document.createElement("table");
  const head = document.createElement("tr");
  addHeader(head, "Name");
  addHeader(head, "Expression");
  table.appendChild(head);
  for (const row of rows) {
    const line = document.createElement("tr");
    addCell(line, row.name);
    addCell(line, row.expression);
    table.appendChild(line);
  }
  host.appendChild(table);
}

async function loadDevices() {
  const rows = await api("/api/devices");
  const host = $("devices");
  host.replaceChildren();
  const table = document.createElement("table");
  const head = document.createElement("tr");
  for (const label of ["Name", "Smart node", "IPv4", "Port"]) {
    addHeader(head, label);
  }
  table.appendChild(head);
  for (const row of rows) {
    const line = document.createElement("tr");
    addCell(line, row.name);
    addCell(line, row.smart_node_id);
    addCell(line, row.ipv4);
    addCell(line, row.port);
    line.addEventListener("click", () => {
      state.deviceId = row.id;
      $("device-name").value = row.name || "";
      $("device-smart-node").value = String(row.smart_node_id);
      $("device-ipv4").value = row.ipv4 || "";
      $("device-port").value = String(row.port);
    });
    table.appendChild(line);
  }
  host.appendChild(table);
}

function passwordSetLabel(row) {
  return row.password_set ? "Set" : "Not set";
}

async function loadServers() {
  const rows = await api("/api/servers");
  const host = $("servers");
  host.replaceChildren();
  const table = document.createElement("table");
  const head = document.createElement("tr");
  for (const label of ["Name", "IPv4", "Port", "Username", "Password"]) {
    addHeader(head, label);
  }
  table.appendChild(head);
  for (const row of rows) {
    const line = document.createElement("tr");
    addCell(line, row.name);
    addCell(line, row.ipv4);
    addCell(line, row.port);
    addCell(line, row.username);
    addCell(line, passwordSetLabel(row));
    line.addEventListener("click", () => fillServer(row));
    table.appendChild(line);
  }
  host.appendChild(table);
}

function fillServer(row) {
  state.serverId = row.id;
  $("server-name").value = row.name || "";
  $("server-win-name").value = row.win_name || "";
  $("server-full-name").value = row.full_name || "";
  $("server-ipv4").value = row.ipv4 || "";
  $("server-port").value = String(row.port);
  $("server-opc").value = row.opc_server_name || "";
  $("server-sql").value = row.sql_server_instance || "";
  $("server-database").value = row.database_name || "";
  $("server-username").value = row.username || "";
  $("server-password").value = "";
}

async function loadStream() {
  const rows = await api("/api/stream");
  const host = $("stream");
  host.replaceChildren();
  const table = document.createElement("table");
  const head = document.createElement("tr");
  for (const label of ["Packet", "Name", "Enc", "Send", "Rate", ""]) {
    addHeader(head, label);
  }
  table.appendChild(head);
  for (const row of rows) {
    const line = document.createElement("tr");
    addCell(line, row.packet_id);
    addCell(line, row.name);
    addCell(line, row.enc_size);
    const sendCell = document.createElement("td");
    const send = document.createElement("input");
    send.type = "checkbox";
    send.checked = Boolean(row.send);
    send.setAttribute("aria-label", "Send " + row.name);
    sendCell.appendChild(send);
    line.appendChild(sendCell);
    const rateCell = document.createElement("td");
    const rate = document.createElement("input");
    rate.type = "number";
    rate.min = "0";
    rate.value = String(row.rate);
    rate.setAttribute("aria-label", "Rate " + row.name);
    rateCell.appendChild(rate);
    line.appendChild(rateCell);
    const action = document.createElement("td");
    const save = document.createElement("button");
    save.type = "button";
    save.textContent = "Save";
    save.addEventListener("click", async () => {
      await api("/api/stream/" + row.packet_id, {
        method: "PUT",
        json: { send: send.checked, rate: Number(rate.value) },
      });
      setStatus("Saved send and rate for " + row.name, false);
      await loadStream();
    });
    action.appendChild(save);
    line.appendChild(action);
    table.appendChild(line);
  }
  host.appendChild(table);
}

async function loadTests() {
  const rows = await api("/api/tests");
  const host = $("tests");
  host.replaceChildren();
  const table = document.createElement("table");
  const head = document.createElement("tr");
  for (const label of ["Name", "Server", "Active"]) {
    addHeader(head, label);
  }
  table.appendChild(head);
  for (const row of rows) {
    const line = document.createElement("tr");
    addCell(line, row.name);
    addCell(line, row.server_id);
    addCell(line, row.active ? "yes" : "no");
    line.addEventListener("click", () => {
      selectTest(row.id).catch((error) => setStatus(error.message, true));
    });
    table.appendChild(line);
  }
  host.appendChild(table);
  if (state.testId !== null) {
    await loadJobs();
  }
}

async function addTest() {
  const created = await api("/api/tests", {
    method: "POST",
    json: {
      name: $("test-name").value.trim(),
      server_id: Number($("test-server").value),
    },
  });
  state.testId = created.id;
  state.logPacketId = null;
  state.logOffset = 0;
  $("log").replaceChildren();
  $("jobs").replaceChildren();
  $("test-name").value = "";
  await loadTests();
  setStatus("Added test " + created.name, false);
}

async function selectTest(testId) {
  state.testId = testId;
  state.logPacketId = null;
  state.logOffset = 0;
  $("log").replaceChildren();
  await loadJobs();
}

async function loadJobs() {
  const host = $("jobs");
  host.replaceChildren();
  if (state.testId === null) {
    return;
  }
  const rows = await api("/api/tests/" + state.testId + "/jobs");
  const table = document.createElement("table");
  const head = document.createElement("tr");
  for (const label of ["Packet", "Done", ""]) {
    addHeader(head, label);
  }
  table.appendChild(head);
  for (const row of rows) {
    const line = document.createElement("tr");
    addCell(line, row.packet_id);
    addCell(line, row.done ? "yes" : "no");
    const action = document.createElement("td");
    if (row.done) {
      const show = document.createElement("button");
      show.type = "button";
      show.textContent = "Show log";
      show.addEventListener("click", () => {
        openLog(row.packet_id).catch((error) => setStatus(error.message, true));
      });
      action.appendChild(show);
      const csv = document.createElement("button");
      csv.type = "button";
      csv.textContent = "CSV";
      csv.addEventListener("click", () => {
        downloadLog(row.packet_id).catch((error) => setStatus(error.message, true));
      });
      action.appendChild(csv);
    }
    line.appendChild(action);
    table.appendChild(line);
  }
  host.appendChild(table);
}

async function openLog(packetId) {
  state.logPacketId = packetId;
  state.logOffset = 0;
  await loadLog();
}

async function loadLog() {
  const host = $("log");
  host.replaceChildren();
  if (state.testId === null || state.logPacketId === null) {
    return;
  }
  const page = await api(
    "/api/tests/" +
      state.testId +
      "/packets/" +
      state.logPacketId +
      "/log?limit=20&offset=" +
      state.logOffset,
  );
  const title = document.createElement("p");
  title.textContent = page.table + " (" + page.total + " rows)";
  host.appendChild(title);
  const table = document.createElement("table");
  const head = document.createElement("tr");
  for (const name of page.columns) {
    addHeader(head, name);
  }
  table.appendChild(head);
  for (const row of page.rows) {
    const line = document.createElement("tr");
    for (const name of page.columns) {
      addCell(line, row[name]);
    }
    table.appendChild(line);
  }
  host.appendChild(table);
  const actions = document.createElement("div");
  actions.className = "actions";
  if (state.logOffset > 0) {
    const previous = document.createElement("button");
    previous.type = "button";
    previous.textContent = "Previous";
    previous.addEventListener("click", () => {
      state.logOffset = Math.max(0, state.logOffset - page.limit);
      loadLog().catch((error) => setStatus(error.message, true));
    });
    actions.appendChild(previous);
  }
  if (state.logOffset + page.rows.length < page.total) {
    const next = document.createElement("button");
    next.type = "button";
    next.textContent = "Next";
    next.addEventListener("click", () => {
      state.logOffset += page.limit;
      loadLog().catch((error) => setStatus(error.message, true));
    });
    actions.appendChild(next);
  }
  host.appendChild(actions);
}

async function downloadLog(packetId) {
  if (state.testId === null) {
    setStatus("Select a test first.", true);
    return;
  }
  const path = "/api/tests/" + state.testId + "/packets/" + packetId + "/log.csv";
  await downloadFile(path, "test-log.csv");
}

function showWorkspace() {
  $("login").hidden = true;
  $("workspace").hidden = false;
  $("sign-out").hidden = false;
}

async function openSession() {
  const token = $("token").value;
  if (!token) {
    setStatus("Enter the operator token.", true);
    return;
  }
  sessionStorage.setItem(TOKEN_KEY, token);
  $("token").value = "";
  try {
    await reloadTree();
    showWorkspace();
    setStatus("", false);
    await showTab("packet");
  } catch (error) {
    sessionStorage.removeItem(TOKEN_KEY);
    setStatus(error.message, true);
  }
}

function signOut() {
  sessionStorage.removeItem(TOKEN_KEY);
  state.tree = [];
  state.selectedId = null;
  state.testId = null;
  state.logPacketId = null;
  state.logOffset = 0;
  clearPacketForm();
  clearFieldForm();
  clearDeviceForm();
  clearServerForm();
  $("node-name").value = "";
  $("node-icon").value = "1";
  $("mapping-connection").value = "";
  $("transform-name").value = "";
  $("transform-expression").value = "";
  $("test-name").value = "";
  $("test-server").value = "";
  $("packet-node").textContent = "Select a node in the tree.";
  for (const id of [
    "tree",
    "fields",
    "mappings",
    "transformations",
    "devices",
    "servers",
    "stream",
    "tests",
    "jobs",
    "log",
  ]) {
    $(id).replaceChildren();
  }
  $("workspace").hidden = true;
  $("sign-out").hidden = true;
  $("login").hidden = false;
  setStatus("", false);
}

async function addNode() {
  const name = $("node-name").value.trim();
  const iconId = Number($("node-icon").value);
  const body = { name, icon_id: iconId };
  if (iconId !== 1) {
    if (state.selectedId === null) {
      setStatus("Select a parent node first.", true);
      return;
    }
    body.parent_id = state.selectedId;
  }
  const created = await api("/api/tree", { method: "POST", json: body });
  await reloadTree();
  await selectNode(created.id);
  setStatus("Added " + created.name, false);
}

async function renameNode() {
  const node = selectedNode();
  if (!node) {
    setStatus("Select a node first.", true);
    return;
  }
  await api("/api/tree/" + node.id, {
    method: "PATCH",
    json: { name: $("node-name").value.trim() },
  });
  await reloadTree();
  await selectNode(node.id);
  setStatus("Renamed.", false);
}

async function moveNode(direction) {
  const node = selectedNode();
  if (!node) {
    setStatus("Select a node first.", true);
    return;
  }
  const index = siblingIndex(node);
  const next = direction < 0 ? index : index + 2;
  if (index < 0 || next < 1) {
    return;
  }
  await api("/api/tree/" + node.id, { method: "PATCH", json: { seq: next } });
  await reloadTree();
  await selectNode(node.id);
}

async function downloadExport(kind, filename) {
  const node = selectedNode();
  if (!node) {
    setStatus("Select a node first.", true);
    return;
  }
  await downloadFile("/api/nodes/" + node.id + "/exports/" + kind, filename);
}

async function downloadFile(path, filename) {
  const token = sessionStorage.getItem(TOKEN_KEY);
  const response = await fetch(path, {
    headers: token ? { Authorization: "Bearer " + token } : {},
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = await response.json();
      if (payload && payload.detail) {
        detail = payload.detail;
      }
    } catch {
      detail = response.statusText;
    }
    throw new Error(detail);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
  setStatus("Downloaded " + filename, false);
}

async function duplicateNode() {
  const node = selectedNode();
  if (!node) {
    setStatus("Select a node first.", true);
    return;
  }
  if (node.icon_id === 1) {
    setStatus("A vehicle is not duplicated.", true);
    return;
  }
  const copied = await api("/api/tree/" + node.id + "/duplicate", { method: "POST" });
  await reloadTree();
  await selectNode(copied.id);
  setStatus("Duplicated as " + copied.name, false);
}

async function deleteNode() {
  const node = selectedNode();
  if (!node) {
    setStatus("Select a node first.", true);
    return;
  }
  await api("/api/tree/" + node.id, { method: "DELETE" });
  state.selectedId = null;
  await reloadTree();
  clearPacketForm();
  setStatus("Deleted " + node.name, false);
}

async function savePacket() {
  const node = selectedNode();
  if (!node) {
    setStatus("Select a node first.", true);
    return;
  }
  const saved = await api("/api/nodes/" + node.id + "/packet", {
    method: "PUT",
    json: {
      packet_id: Number($("packet-id").value),
      name: $("packet-name").value.trim(),
      is_input: $("packet-is-input").checked,
    },
  });
  await reloadTree();
  await selectNode(node.id);
  state.packet = saved;
  text("enc-size", saved.enc_size);
  text("dec-size", saved.dec_size);
  setStatus("Saved packet " + saved.packet_id, false);
}

async function calcSizes() {
  const node = selectedNode();
  if (!node) {
    setStatus("Select a node first.", true);
    return;
  }
  await api("/api/nodes/" + node.id + "/sizes", { method: "POST" });
  await loadPacket();
  setStatus("Calculated sizes.", false);
}

async function saveField() {
  if (!state.packet) {
    setStatus("Save a packet first.", true);
    return;
  }
  const seqRaw = $("field-seq").value.trim();
  const body = {
    name: $("field-name").value.trim(),
    type_id: Number($("field-type-id").value),
    qty: Number($("field-qty").value),
    override: $("field-override").checked,
  };
  let saved;
  if (state.fieldId === null) {
    if (seqRaw !== "") {
      body.seq = Number(seqRaw);
    }
    saved = await api("/api/vartypes/" + state.packet.var_type_id + "/fields", {
      method: "POST",
      json: body,
    });
  } else {
    body.seq = seqRaw === "" ? null : Number(seqRaw);
    saved = await api("/api/fields/" + state.fieldId, { method: "PATCH", json: body });
  }
  state.fieldId = saved.id;
  await loadFields();
  setStatus("Saved field.", false);
}

function clearFieldForm() {
  state.fieldId = null;
  $("field-name").value = "";
  $("field-type-id").value = "";
  $("field-qty").value = "1";
  $("field-seq").value = "";
  $("field-override").checked = false;
}

async function addTransformation() {
  await api("/api/transformations", {
    method: "POST",
    json: {
      name: $("transform-name").value.trim(),
      expression: $("transform-expression").value.trim(),
    },
  });
  $("transform-name").value = "";
  $("transform-expression").value = "";
  await loadTransformations();
  setStatus("Added transformation.", false);
}

async function saveDevice() {
  const body = {
    name: $("device-name").value.trim(),
    smart_node_id: Number($("device-smart-node").value),
    ipv4: $("device-ipv4").value.trim(),
    port: Number($("device-port").value),
  };
  const saved = state.deviceId === null
    ? await api("/api/devices", { method: "POST", json: body })
    : await api("/api/devices/" + state.deviceId, { method: "PATCH", json: body });
  state.deviceId = saved.id;
  await loadDevices();
  setStatus("Saved device.", false);
}

function clearDeviceForm() {
  state.deviceId = null;
  $("device-name").value = "";
  $("device-smart-node").value = "";
  $("device-ipv4").value = "";
  $("device-port").value = "2357";
}

function serverBody(includePassword) {
  const body = {
    name: $("server-name").value.trim(),
    win_name: $("server-win-name").value.trim(),
    full_name: $("server-full-name").value.trim(),
    ipv4: $("server-ipv4").value.trim(),
    port: Number($("server-port").value),
    opc_server_name: $("server-opc").value.trim(),
    sql_server_instance: $("server-sql").value.trim(),
    database_name: $("server-database").value.trim(),
    username: $("server-username").value.trim(),
  };
  const password = $("server-password").value;
  if (includePassword) {
    body.password = password;
  }
  $("server-password").value = "";
  return body;
}

async function saveServer() {
  const creating = state.serverId === null;
  const saved = creating
    ? await api("/api/servers", { method: "POST", json: serverBody(true) })
    : await api("/api/servers/" + state.serverId, {
        method: "PATCH",
        json: serverBody($("server-password").value !== ""),
      });
  state.serverId = saved.id;
  await loadServers();
  setStatus("Saved server " + saved.name, false);
}

function clearServerForm() {
  state.serverId = null;
  for (const id of [
    "server-name",
    "server-win-name",
    "server-full-name",
    "server-ipv4",
    "server-opc",
    "server-sql",
    "server-database",
    "server-username",
    "server-password",
  ]) {
    $(id).value = "";
  }
  $("server-port").value = "2357";
}

function bind(id, action) {
  $(id).addEventListener("click", async () => {
    try {
      await action();
    } catch (error) {
      setStatus(error.message, true);
    }
  });
}

function bindTabs() {
  for (const button of document.querySelectorAll(".tab")) {
    button.addEventListener("click", async () => {
      try {
        await showTab(button.getAttribute("data-tab") || "packet");
      } catch (error) {
        setStatus(error.message, true);
      }
    });
  }
}

bind("open-session", openSession);
bind("sign-out", signOut);
bind("add-node", addNode);
bind("rename-node", renameNode);
bind("move-up", () => moveNode(-1));
bind("move-down", () => moveNode(1));
bind("duplicate-node", duplicateNode);
bind("delete-node", deleteNode);
bind("link-mapping", linkMapping);
bind("save-packet", savePacket);
bind("calc-sizes", calcSizes);
bind("export-simulink", () => downloadExport("simulink", "simulink.csv"));
bind("export-mapping", () => downloadExport("mapping", "mapping.csv"));
bind("export-opcua", () => downloadExport("opcua", "opcua-nodes.txt"));
bind("save-field", saveField);
bind("clear-field", async () => clearFieldForm());
bind("add-transform", addTransformation);
bind("save-device", saveDevice);
bind("clear-device", async () => clearDeviceForm());
bind("add-test", addTest);
bind("save-server", saveServer);
bind("clear-server", async () => clearServerForm());
bindTabs();

const existing = sessionStorage.getItem(TOKEN_KEY);
if (existing) {
  api("/api/tree")
    .then(async (rows) => {
      state.tree = rows;
      showWorkspace();
      renderTree();
      await showTab("packet");
    })
    .catch(() => {
      sessionStorage.removeItem(TOKEN_KEY);
    });
}
