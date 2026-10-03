-- =====================================================================
-- Astra ground station databases (AstraConfig + AstraTestLog)
-- 03 - views, functions (translated stored procedures), trigger
-- Dialect: PostgreSQL 13+ (tested on 16), run with psql -v ON_ERROR_STOP=1 after 02_data.sql
-- Hand translation of the T-SQL objects in mssql/03_programmability.sql. Every object carries a comment naming
-- its SQL Server original; behavioural differences are flagged with "Note" / "Difference" comments and listed
-- in README.md. Not translated (SSMS database-diagram support only): dbo.sysdiagrams, dbo.fn_diagramobjects,
-- dbo.sp_alterdiagram, sp_creatediagram, sp_dropdiagram, sp_helpdiagramdefinition, sp_helpdiagrams,
-- sp_renamediagram, sp_upgraddiagrams.
-- =====================================================================
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SET client_min_messages = warning;
SET check_function_bodies = on;

-- =====================================================================
-- SCHEMA config  (from AstraConfig.dbo)
-- =====================================================================
SET search_path = config;

-- Views ----------------------------------------------------------------
-- Translation rules used for every view:
--   [x] / dbo.x -> lower-case identifier (quoted only for "order", "group", "grouping", "conn part no", names with spaces)
--   TOP (100) PERCENT / TOP 9223372036854775807 WITH TIES ... ORDER BY -> plain ORDER BY (PG keeps it in the view)
--   ISNULL(a,b) -> COALESCE(a,b);  string + -> ||;  bit = 1 -> boolean = true
--   ORDER BY x  -> ORDER BY x NULLS FIRST  (SQL Server sorts NULLs first ascending, PG sorts them last by default)

-- dbo.[Links Viewer]  (SSMA for Access)
CREATE VIEW "links viewer" AS
SELECT links.*, stage.stage, area_list.area_name, areas.ordering
FROM board
   INNER JOIN ((stage
   INNER JOIN (area_list
   INNER JOIN areas
   ON area_list.id = areas.area_id)
   ON stage.id = areas.stage_id)
   INNER JOIN links
   ON areas.id = links.area_id)
   ON board.id = links.board_id
ORDER BY stage.stage NULLS FIRST, areas.ordering NULLS FIRST, board.id NULLS FIRST, links.c1_first_pin NULLS FIRST;

-- dbo.[Links and Names]  (SSMA for Access)
CREATE VIEW "links and names" AS
SELECT links.c2_first_pin, links.c2_type_id, links.board_id, links.c1_first_pin, links.c1_type_id,
       links.link_type_id, links.area_id, names.link_description, names.short_name
FROM names
   INNER JOIN links
   ON names.id = links.names_id;

-- dbo.Pinout_Details  (SSMA for Access)
CREATE VIEW pinout_details AS
SELECT stage.stage, area_list.area_name, board.board_connector, links.c1_first_pin,
       connectors_1."conn part no" AS c1, names.link_description, names.short_name,
       connectors."conn part no" AS c2, links.c2_first_pin
FROM stage
   INNER JOIN (area_list
   INNER JOIN ((names
   INNER JOIN (connectors
   RIGHT JOIN (areas
   INNER JOIN (board
   INNER JOIN links
   ON board.id = links.board_id)
   ON areas.id = links.area_id)
   ON connectors.id = links.c2_type_id)
   ON names.id = links.names_id)
   LEFT JOIN connectors AS connectors_1
   ON links.c1_type_id = connectors_1.id)
   ON area_list.id = areas.area_id)
   ON stage.id = areas.stage_id
ORDER BY area_list.area_order NULLS FIRST, stage.stage_order NULLS FIRST, board."order" NULLS FIRST, links.c1_first_pin NULLS FIRST;

-- dbo.Pinouts  (SSMA for Access)
CREATE VIEW pinouts AS
SELECT names.link_description, names.short_name, stage.stage, area_list.area_name, board.board_connector,
       links.c1_first_pin, connectors."conn part no" AS c1type
FROM stage
   INNER JOIN ((area_list
   INNER JOIN areas
   ON area_list.id = areas.area_id)
   INNER JOIN (board
   INNER JOIN (connectors
   INNER JOIN (names
   INNER JOIN links
   ON names.id = links.names_id)
   ON connectors.id = links.c1_type_id)
   ON board.id = links.board_id)
   ON areas.id = links.area_id)
   ON stage.id = areas.stage_id
ORDER BY stage.id NULLS FIRST, areas.ordering NULLS FIRST, area_list.area_name NULLS FIRST, board.board_connector NULLS FIRST, links.c1_first_pin NULLS FIRST;

-- dbo.View_1
CREATE VIEW view_1 AS
SELECT a.name AS area, b.name AS board, c.firstpin, i.name AS interface, c.shortname, c.description, c.id AS connectionid
FROM connections AS c
   INNER JOIN treeversions AS b ON c.boardid = b.id
   INNER JOIN treeversions AS a ON b.parentid = a.id
   INNER JOIN treeversions AS h ON a.parentid = h.id
   INNER JOIN treeversions AS i ON h.parentid = i.parentid
WHERE (i.iconid = 6 OR i.iconid = 7) AND (h.iconid = 8) AND (a.iconid = 9) AND (b.iconid = 10)
ORDER BY a.seq NULLS FIRST, a.name NULLS FIRST, b.name NULLS FIRST, b.seq NULLS FIRST, c.firstpin NULLS FIRST;

-- dbo.View_2
CREATE VIEW view_2 AS
SELECT c.boardid, m.connectionid
FROM treeversions AS i
   INNER JOIN vartypes AS r ON i.id = r.scopeid
   INNER JOIN fields AS f ON r.id = f.vartypeid
   INNER JOIN mappings AS m ON f.id = m.fieldid
   INNER JOIN treeversions AS h ON i.parentid = h.parentid
   INNER JOIN treeversions AS a ON h.id = a.parentid
   INNER JOIN treeversions AS b ON a.id = b.parentid
   INNER JOIN connections AS c ON m.connectionid = c.id AND b.id = c.boardid
WHERE (i.id = 7) AND (m.fieldid = 235);

-- dbo.View_3   (TOP (1) ... ORDER BY -> ORDER BY ... LIMIT 1)
CREATE VIEW view_3 AS
SELECT n.id AS nodeid
FROM treeversions AS s
   INNER JOIN treeversions AS v ON s.id = v.parentid
   INNER JOIN treeversions AS r ON v.id = r.parentid
   INNER JOIN treeversions AS n ON r.id = n.parentid
   INNER JOIN treeversions AS i ON n.id = i.parentid
WHERE (s.name = 'Stage 1') AND (i.name = 'IRIG106') AND (n.iconid = 5)
ORDER BY v.name DESC NULLS LAST, r.name DESC NULLS LAST
LIMIT 1;

-- dbo.gen_Interface_Signals_All  (SSMA for Access)
CREATE VIEW gen_interface_signals_all AS
SELECT "grouping"."group", "grouping".short_name AS grouping_short_name, "grouping".description, "grouping".multiple,
       names.internal_name, interfaces.array_length, signal_data_types.data_type,
       names.short_name AS names_short_name, names.link_description, interfaces.override, interface_list.label
FROM signal_data_types
   INNER JOIN (names
   INNER JOIN (interface_list
   INNER JOIN ("grouping"
   RIGHT JOIN interfaces
   ON "grouping".id = interfaces.group_id)
   ON interface_list.id = interfaces.interface_id)
   ON names.id = interfaces.name_id)
   ON signal_data_types.id = interfaces.data_type_id
ORDER BY "grouping"."order" NULLS FIRST, interfaces."order" NULLS FIRST, names.internal_name NULLS FIRST;

-- dbo.gen_Links_Sorted_For_Mapping  (SSMA for Access)
CREATE VIEW gen_links_sorted_for_mapping AS
SELECT links.id, links.names_id, areas.stage_id AS stagealias, stage.stage_order, links.area_id,
       areas.ordering AS area_order, links.board_id, board."order" AS board_order, links.c1_first_pin
FROM stage
   INNER JOIN (areas
   INNER JOIN (board
   INNER JOIN links
   ON board.id = links.board_id)
   ON areas.id = links.area_id)
   ON stage.id = areas.stage_id
ORDER BY stage.stage_order NULLS FIRST, areas.ordering NULLS FIRST, board."order" NULLS FIRST, links.c1_first_pin NULLS FIRST;

-- dbo.gen_Sequence_to_Interface_Mapping_All  (SSMA for Access)
CREATE VIEW gen_sequence_to_interface_mapping_all AS
SELECT interface_list.label, "grouping"."group" AS group1, "grouping".multiple AS multiple1, names.internal_name AS name1,
       "grouping".short_name AS group2, "grouping".multiple AS multiple2, names.short_name AS name2
FROM names
   INNER JOIN (interface_list
   INNER JOIN ("grouping"
   RIGHT JOIN interfaces
   ON "grouping".id = interfaces.group_id)
   ON interface_list.id = interfaces.interface_id)
   ON names.id = interfaces.name_id
WHERE (((interfaces.insequence) = true))
ORDER BY interface_list.label NULLS FIRST, "grouping"."order" NULLS FIRST, names.internal_name NULLS FIRST;

-- dbo.make_Interface_Names  (SSMA for Access)
CREATE VIEW make_interface_names AS
SELECT names.link_description, names.short_name, names.internal_name, interfaces.interface_id, interfaces.group_id,
       interfaces.name_id, interfaces.data_type_id, interfaces.array_length
FROM names
   RIGHT JOIN interfaces
   ON names.id = interfaces.name_id;

-- dbo.review_Interfaces  (SSMA for Access)
CREATE VIEW review_interfaces AS
SELECT interfaces.id, interfaces.interface_id, interfaces.group_id, "grouping".multiple, interfaces.name_id,
       interfaces.data_type_id, interfaces.array_length, interfaces.override, interfaces.insequence,
       "grouping"."order" AS grouping_order, interfaces."order" AS interfaces_order
FROM names
   RIGHT JOIN ("grouping"
   RIGHT JOIN interfaces
   ON "grouping".id = interfaces.group_id)
   ON names.id = interfaces.name_id
ORDER BY interfaces.interface_id NULLS FIRST, "grouping"."order" NULLS FIRST, "grouping"."group" NULLS FIRST,
         interfaces."order" NULLS FIRST, names.internal_name NULLS FIRST;

-- dbo.viewConnections
CREATE VIEW viewconnections AS
SELECT n.name AS node, h.name AS hardware, a.name AS area, b.name AS board, n.id AS nodeid, h.id AS hardwareid,
       a.id AS areaid, b.id AS boardid, connections.id AS connectionid, connections.firstpin
FROM treeversions AS b
   INNER JOIN treeversions AS a ON b.parentid = a.id
   INNER JOIN treeversions AS h ON a.parentid = h.id
   INNER JOIN treeversions AS n ON h.parentid = n.id
   INNER JOIN connections ON b.id = connections.boardid
WHERE (n.iconid = 5);

-- dbo.viewGroups
CREATE VIEW viewgroups AS
SELECT g."group" AS groupname, g.multiple AS qty, g."order" AS grouporder, l.label AS interfacename
FROM interface_list AS l
   INNER JOIN interfaces AS i ON l.id = i.interface_id
   LEFT OUTER JOIN "grouping" AS g ON i.group_id = g.id
GROUP BY g."group", g.multiple, g."order", l.label
HAVING (g."group" IS NOT NULL)
ORDER BY grouporder NULLS FIRST;

-- dbo.viewInterfaces   (unparenthesised nested joins made explicit; same join tree)
CREATE VIEW viewinterfaces AS
SELECT "grouping"."group" AS groupname, "grouping".description AS groupdescription, COALESCE("grouping".multiple, 1) AS multiple,
       names.internal_name AS varname, COALESCE(interfaces.array_length, 1) AS arraylen, signal_data_types.data_type,
       names.link_description AS vardescription, interfaces.override, interface_list.label AS interfacename,
       interface_list.description AS interfacedescription, COALESCE("grouping"."order", 0) AS groupingorder,
       interfaces."order" AS varorder
FROM signal_data_types
   INNER JOIN (names
   INNER JOIN (interface_list
   INNER JOIN ("grouping"
   RIGHT OUTER JOIN interfaces ON "grouping".id = interfaces.group_id)
   ON interface_list.id = interfaces.interface_id)
   ON names.id = interfaces.name_id)
   ON signal_data_types.id = interfaces.data_type_id;

-- dbo.viewLinks   (its stored definition still says CREATE VIEW dbo.review_Interface_To_Links_Mapping: it was
--                  renamed with sp_rename; the real name is viewLinks)
CREATE VIEW viewlinks AS
SELECT interface_list.label AS interfacename, "grouping"."group" AS groupname, n1.internal_name AS varname,
       signal_data_types.data_type AS datatype, area_list.area_name AS area, board.board_connector AS board,
       n2.short_name AS linkname, n2.link_description AS linkdescription, link_type.link_type AS linktype,
       links.c1_first_pin, links.c1_type_id, interfacerowtolink.link_id, interfacerowtolink.interface_row_id AS field_id
FROM links
   INNER JOIN (interfaces
   INNER JOIN interfacerowtolink ON interfaces.id = interfacerowtolink.interface_row_id)
   ON links.id = interfacerowtolink.link_id
   INNER JOIN interface_list ON interfaces.interface_id = interface_list.id
   INNER JOIN "grouping" ON interfaces.group_id = "grouping".id
   INNER JOIN names AS n1 ON interfaces.name_id = n1.id
   INNER JOIN signal_data_types ON interfaces.data_type_id = signal_data_types.id
   INNER JOIN board ON links.board_id = board.id
   INNER JOIN names AS n2 ON links.names_id = n2.id
   INNER JOIN link_type ON links.link_type_id = link_type.id
   INNER JOIN areas ON links.area_id = areas.id
   INNER JOIN area_list ON areas.area_id = area_list.id
WHERE (areas.stage_id = 1) OR (areas.stage_id = 4);

-- dbo.viewConnectionsToImport
-- NOTE: BROKEN in the source database: it references dbo.review_Interface_To_Links_Mapping, which no longer exists
--       (renamed to viewLinks). Re-created against viewlinks, same as in mssql/03_programmability.sql.
CREATE VIEW viewconnectionstoimport AS
SELECT tboards.id AS boardid, vartypes.scopeid AS nodeid, viewlinks.c1_first_pin AS firstpin, tvars.id AS fieldid
FROM treeversions AS tinterfaces
   INNER JOIN viewlinks ON tinterfaces.name = viewlinks.interfacename
   INNER JOIN vartypes AS tpackets ON tinterfaces.id = tpackets.scopeid
   INNER JOIN fields AS tgroups ON tpackets.id = tgroups.vartypeid AND viewlinks.groupname = tgroups.name
   INNER JOIN fields AS tvars ON viewlinks.varname = tvars.name
   INNER JOIN vartypes ON tinterfaces.id = vartypes.scopeid AND tvars.vartypeid = vartypes.id
   INNER JOIN treeversions AS tareas ON viewlinks.area = tareas.name
   INNER JOIN treeversions AS tboards ON tareas.id = tboards.parentid AND viewlinks.board = tboards.name
WHERE (tinterfaces.iconid = 6 OR tinterfaces.iconid = 7) AND (tgroups.typeid >= 100) AND (tgroups.vartypeid >= 100)
  AND (tareas.iconid = 9) AND (tboards.iconid = 10);

-- dbo.view_InterfaceInfo
CREATE VIEW view_interfaceinfo AS
SELECT treeversions.id, vartypes.description AS interfacedescription, packets.isinput
FROM treeversions
   INNER JOIN packets ON treeversions.id = packets.nodeid
   INNER JOIN vartypes ON packets.vartypeid = vartypes.id;

-- dbo.view_Interfaces
CREATE VIEW view_interfaces AS
SELECT n.name AS node, i.name AS interfacename, view_interfaceinfo.interfacedescription, r.name AS groupname,
       vartypes.description AS groupdescription, r.qty AS multiple, f.name AS varname, f.qty AS arraylen,
       vartypenames.name AS data_type, f.description AS vardescription, f.override, f.id AS fieldid
FROM vartypes
   INNER JOIN fields AS r ON vartypes.id = r.typeid
   INNER JOIN fields AS f ON r.typeid = f.vartypeid
   INNER JOIN vartypes AS vartypenames ON f.typeid = vartypenames.id
   INNER JOIN treeversions AS i ON vartypes.scopeid = i.id
   INNER JOIN view_interfaceinfo ON i.id = view_interfaceinfo.id
   INNER JOIN treeversions AS n ON i.parentid = n.id
WHERE (r.typeid >= 100);

-- dbo.viewLinksToMappings
CREATE VIEW viewlinkstomappings AS
SELECT f.interfacename, f.varname AS fieldname, l.field_id, l.link_id, f.fieldid, c.connectionid
FROM viewlinks AS l
   INNER JOIN view_interfaces AS f ON l.interfacename = f.interfacename AND l.groupname = f.groupname AND l.varname = f.varname
   INNER JOIN viewconnections AS c ON f.node = c.node AND l.area = c.area AND l.board = c.board AND l.c1_first_pin = c.firstpin
ORDER BY f.interfacename NULLS FIRST, f.varname NULLS FIRST, f.fieldid NULLS FIRST;

-- dbo.viewMappingSortedByConnections
CREATE VIEW viewmappingsortedbyconnections AS
SELECT a.name AS area, b.name AS board, c.firstpin, i.name AS interface, t.name AS record, f.name AS field, n.id
FROM connections AS c
   INNER JOIN treeversions AS b ON c.boardid = b.id
   INNER JOIN treeversions AS a ON b.parentid = a.id
   INNER JOIN treeversions AS h ON a.parentid = h.id
   INNER JOIN treeversions AS i ON h.parentid = i.parentid
   INNER JOIN vartypes AS t ON i.id = t.scopeid
   INNER JOIN fields AS f ON t.id = f.vartypeid AND c.id = f.connectionid
   INNER JOIN treeversions AS n ON h.parentid = n.id
WHERE (h.iconid = 8) AND (n.id = 5);

-- dbo.viewPacketMainRecord
CREATE VIEW viewpacketmainrecord AS
SELECT treeversions.name AS interfacename, fields.name AS fieldname,
       COALESCE(fields.description, vartypenames.description) AS fielddescription, fields.qty AS multiple,
       vartypenames.name AS data_type, packets.vartypeid
FROM vartypes AS vartypenames
   INNER JOIN (packets
   INNER JOIN treeversions ON packets.nodeid = treeversions.id
   INNER JOIN fields ON packets.vartypeid = fields.vartypeid)
   ON vartypenames.id = fields.typeid;

-- dbo.viewPacketFields
CREATE VIEW viewpacketfields AS
SELECT viewpacketmainrecord.interfacename, viewpacketmainrecord.fieldname AS groupname,
       viewpacketmainrecord.fielddescription AS groupdescription, viewpacketmainrecord.multiple
FROM vartypes
   INNER JOIN fields ON vartypes.id = fields.vartypeid
   CROSS JOIN viewpacketmainrecord;

-- dbo.viewParts
CREATE VIEW viewparts AS
SELECT parts.id, partlists.name, partlists.prefix, partlists.version, partstatus.name AS status, locations.location,
       parts.customization, parts.description, parts.mcu_uid, parts.legacysn, parts.coated
FROM parts
   INNER JOIN partlists ON parts.partlistid = partlists.id
   INNER JOIN locations ON parts.locationid = locations.id
   INNER JOIN partstatus ON parts.statusid = partstatus.id
ORDER BY parts.id DESC NULLS LAST;

-- dbo.viewTableDependencies   (INFORMATION_SCHEMA exists in PG too; restricted to schema config, which is what
--                              the SQL Server view saw: every table of AstraConfig lives in dbo). Column naming
--                              (TableWithPK is really the referencing table) kept exactly as in the original.
CREATE VIEW viewtabledependencies AS
SELECT t1.table_name::varchar(128) AS tablewithpk, tc2.table_name::varchar(128) AS tablewithfk
FROM information_schema.tables AS t1
   INNER JOIN information_schema.table_constraints AS tc1
      ON t1.table_catalog = tc1.table_catalog AND t1.table_schema = tc1.table_schema AND t1.table_name = tc1.table_name
   INNER JOIN information_schema.referential_constraints AS rc
      ON tc1.constraint_catalog = rc.constraint_catalog AND tc1.constraint_schema = rc.constraint_schema AND tc1.constraint_name = rc.constraint_name
   INNER JOIN information_schema.table_constraints AS tc2
      ON rc.unique_constraint_catalog = tc2.constraint_catalog AND rc.unique_constraint_schema = tc2.constraint_schema
     AND rc.unique_constraint_name = tc2.constraint_name
WHERE (t1.table_type = 'BASE TABLE') AND (tc1.constraint_type = 'FOREIGN KEY') AND t1.table_schema = 'config';

-- dbo.view_InterfacesPerTest
CREATE VIEW view_interfacespertest AS
SELECT n.name AS smartnodename, d.ipv4, d.port, i.name AS interfacename, p.isinput,
       '\\' || s.fullname || '\' || v.name || '\' AS libraryname
FROM actors AS a
   INNER JOIN devices AS d ON a.deviceid = d.id
   INNER JOIN treeversions AS n ON d.smartnodeid = n.id
   INNER JOIN treeversions AS i ON n.id = i.parentid
   INNER JOIN packets AS p ON i.id = p.nodeid
   INNER JOIN vartypes AS v ON p.vartypeid = v.id
   INNER JOIN tests AS t ON a.testid = t.id
   INNER JOIN servers AS s ON t.serverid = s.id
WHERE (a.testid = 1);

-- Stored procedures -> PL/pgSQL functions ------------------------------------------------------------
-- Conventions (apply to every function below):
--  * Each T-SQL procedure becomes a FUNCTION (not a PROCEDURE): FireDAC (RAD Studio 10.2) calls PG functions via
--    TFDStoredProc / SELECT, and PG procedures cannot return result sets the way T-SQL procs do.
--      - proc that ends with a SELECT          -> RETURNS TABLE(...) / RETURNS SETOF config.<table>
--      - proc with OUTPUT parameters           -> INOUT parameters (DEFAULT NULL), function returns one row
--      - proc with neither                     -> RETURNS void
--    Call as:  SELECT * FROM config.spgetintfs(5);   SELECT * FROM config.spgetvartype(6);   SELECT config.spdelete(42);
--  * Parameter names are the original names without '@', folded to lower case (FireDAC param names = those).
--    Inside the body every parameter is copied to a local p_<name>, and '#variable_conflict use_column' makes any
--    unqualified name that is also a column resolve to the column, as it would in T-SQL.
--  * SET @v = (SELECT ...)      -> v := (SELECT ...)      (identical: NULL if no row, error if >1 row)
--    SELECT @v = col FROM ...   -> FOR r IN SELECT ... LOOP v := r.col; END LOOP;
--                                  (identical: variables keep their old value when no row matches, last row wins)
--    @@IDENTITY                 -> INSERT ... RETURNING id INTO v
--    #temp tables / table vars  -> CTEs, arrays or set-returning helper functions (temp tables are session-scoped
--                                  in PG and would collide in the recursive spDuplicate*/spDelete* call chains)
--    INSERT ... SELECT ... ORDER BY into an IDENTITY(1,1) column -> row_number() OVER (ORDER BY ...)
--    getdate()                  -> LOCALTIMESTAMP;  ISNULL -> COALESCE;  bit 1/0 -> true/false
--    ORDER BY x                 -> ORDER BY x NULLS FIRST (SQL Server puts NULLs first ascending)

-- Migration helper (no T-SQL counterpart): emulates SET IDENTITY_INSERT semantics. In SQL Server an explicit value
-- larger than the current identity moves the identity forward; a PG identity sequence does not move by itself.
CREATE FUNCTION identity_insert_bump(p_table text, p_column text, p_value bigint)
RETURNS void
LANGUAGE plpgsql
AS $fn$
DECLARE
    v_seq text := pg_get_serial_sequence(p_table, p_column);
    v_last bigint;
    v_called boolean;
BEGIN
    EXECUTE format('SELECT last_value, is_called FROM %s', v_seq) INTO v_last, v_called;
    IF NOT v_called THEN v_last := v_last - 1; END IF;
    IF p_value > v_last THEN
        PERFORM setval(v_seq, p_value, true);
    END IF;
END
$fn$;
COMMENT ON FUNCTION identity_insert_bump(text, text, bigint) IS 'Migration helper: emulates SQL Server IDENTITY_INSERT moving the identity counter forward';

-- ---------------------------------------------------------------------------------------------------
-- dbo.GetVarTypesInTopologicalOrder(@NodeID)  -> RETURNS TABLE(id, vartypeid)
-- Kahn topological sort of the record types (VarTypes) declared under a node. The @Edges / @VarTypes /
-- @VarTypeList table variables become arrays; the result is identical (same MIN(VarTypeID) choice each step).
-- Difference: the T-SQL @Edges table has PRIMARY KEY(FieldRecordID, RecordID), so a record with two fields of the
-- same record type makes the T-SQL INSERT fail (PK violation; @Edges stays empty). Here duplicate edges are
-- collapsed with DISTINCT. No such duplicates exist in the migrated data.
CREATE FUNCTION getvartypesintopologicalorder(nodeid integer)
RETURNS TABLE(id integer, vartypeid integer)
LANGUAGE plpgsql
SET search_path = config
AS $fn$
#variable_conflict use_column
DECLARE
    p_nodeid  integer := nodeid;
    e_from    integer[];   -- FieldRecordID (type used by a field)
    e_to      integer[];   -- RecordID (record that owns the field)
    v_free    integer[];   -- @VarTypes
    v_newfree integer[];
    v_id      integer;
    v_n       integer := 0;
BEGIN
    SELECT COALESCE(array_agg(x.typeid), '{}'), COALESCE(array_agg(x.recid), '{}')
      INTO e_from, e_to
      FROM (SELECT DISTINCT f.typeid, t.id AS recid
              FROM vartypes t INNER JOIN fields f ON t.id = f.vartypeid
             WHERE (t.scopeid = p_nodeid) AND (f.typeid >= 100)) x;

    v_free := ARRAY(SELECT vt.id FROM vartypes vt
                     WHERE (vt.scopeid = p_nodeid) AND NOT (vt.id = ANY (e_to)));

    WHILE cardinality(v_free) > 0 LOOP
        v_id   := (SELECT min(x) FROM unnest(v_free) x);
        v_free := array_remove(v_free, v_id);

        v_n := v_n + 1;
        id := v_n; vartypeid := v_id;
        RETURN NEXT;

        -- records whose only remaining incoming edges came from v_id become free
        v_newfree := ARRAY(SELECT e.r FROM unnest(e_from, e_to) AS e(f, r)
                            WHERE e.f = v_id
                              AND NOT EXISTS (SELECT 1 FROM unnest(e_from, e_to) AS e2(f, r)
                                               WHERE e2.f <> v_id AND e2.r = e.r));
        -- remove the edges leaving v_id
        SELECT COALESCE(array_agg(e.f), '{}'), COALESCE(array_agg(e.r), '{}')
          INTO e_from, e_to
          FROM unnest(e_from, e_to) AS e(f, r)
         WHERE e.f <> v_id;
        v_free := v_free || v_newfree;
    END LOOP;
    -- At this point the edge list should be empty (otherwise there is a cycle; those types are not returned)
END
$fn$;

-- ---------------------------------------------------------------------------------------------------
-- dbo.GetTablesInTopologicalOrder  -> RETURNS TABLE(id, tablename)
-- Same algorithm over viewtabledependencies. Table names are the PG (lower-case) names of schema config.
-- "TOP 1 TableName ORDER BY TableName" uses the mssql_order collation (SQL Server-like ordering).
-- Difference: SQL Server also lists dbo.sysdiagrams (SSMS diagram table), which is not migrated.
CREATE FUNCTION gettablesintopologicalorder()
RETURNS TABLE(id integer, tablename varchar(128))
LANGUAGE plpgsql
SET search_path = config
AS $fn$
#variable_conflict use_column
DECLARE
    e_fk     text[];   -- FKTable
    e_pk     text[];   -- PKTable
    v_tables text[];   -- @Tables
    v_new    text[];
    v_name   text;
    v_n      integer := 0;
BEGIN
    SELECT COALESCE(array_agg(x.tablewithfk), '{}'), COALESCE(array_agg(x.tablewithpk), '{}')
      INTO e_fk, e_pk
      FROM (SELECT DISTINCT d.tablewithfk::text, d.tablewithpk::text FROM viewtabledependencies d) x;

    v_tables := ARRAY(SELECT t.table_name::text FROM information_schema.tables t
                       WHERE t.table_schema = 'config' AND t.table_type = 'BASE TABLE'
                         AND NOT (t.table_name::text = ANY (e_pk)));

    WHILE cardinality(v_tables) > 0 LOOP
        v_name   := (SELECT x FROM unnest(v_tables) x ORDER BY x COLLATE mssql_order LIMIT 1);
        v_tables := array_remove(v_tables, v_name);

        v_n := v_n + 1;
        id := v_n; tablename := v_name;
        RETURN NEXT;

        v_new := ARRAY(SELECT e.p FROM unnest(e_fk, e_pk) AS e(f, p)
                        WHERE e.f = v_name
                          AND NOT EXISTS (SELECT 1 FROM unnest(e_fk, e_pk) AS e2(f, p)
                                           WHERE e2.f <> v_name AND e2.p = e.p));
        SELECT COALESCE(array_agg(e.f), '{}'), COALESCE(array_agg(e.p), '{}')
          INTO e_fk, e_pk
          FROM unnest(e_fk, e_pk) AS e(f, p)
         WHERE e.f <> v_name;
        v_tables := v_tables || v_new;
    END LOOP;
END
$fn$;

-- ---------------------------------------------------------------------------------------------------
-- dbo.spCalcVarTypeSizes(@NodeID)  (used by the bridge) -> RETURNS void
CREATE FUNCTION spcalcvartypesizes(nodeid integer)
RETURNS void
LANGUAGE plpgsql
SET search_path = config
AS $fn$
#variable_conflict use_column
DECLARE
    p_nodeid integer := nodeid;
    v_ids    integer[];
    v_vartypeid integer;
BEGIN
    -- #V
    v_ids := ARRAY(SELECT g.vartypeid FROM getvartypesintopologicalorder(p_nodeid) g ORDER BY g.id);

    FOREACH v_vartypeid IN ARRAY v_ids LOOP
        UPDATE vartypes
           SET decsize = 0,
               encsize = 0
         WHERE id = v_vartypeid;

        UPDATE vartypes
           SET decsize = (SELECT SUM(f.qty * t.decsize) FROM fields f INNER JOIN vartypes t ON f.typeid = t.id WHERE f.vartypeid = v_vartypeid),
               encsize = (SELECT SUM(f.qty * t.encsize) FROM fields f INNER JOIN vartypes t ON f.typeid = t.id WHERE f.vartypeid = v_vartypeid)
         WHERE id = v_vartypeid;

        UPDATE vartypes
           SET decsize = decsize + 8 * (SELECT COUNT(*) FROM fields f INNER JOIN vartypes t ON f.typeid = t.id WHERE f.vartypeid = v_vartypeid AND f.override = true),
               encsize = encsize +     (SELECT COUNT(*) FROM fields f INNER JOIN vartypes t ON f.typeid = t.id WHERE f.vartypeid = v_vartypeid AND f.override = true)
         WHERE id = v_vartypeid;
    END LOOP;

    UPDATE vartypes
       SET decsize = decsize / 8,                 -- integer division, as in T-SQL
           encsize = CEILING(encsize / 8.0)
     WHERE id = ANY (v_ids);
END
$fn$;

-- ---------------------------------------------------------------------------------------------------
-- dbo.spGetVarType(@NodeID, @VarTypeID OUT, @Name OUT, @Description OUT, @DecSize OUT, @EncSize OUT)  (bridge)
CREATE FUNCTION spgetvartype(nodeid integer,
                             INOUT vartypeid integer DEFAULT NULL,
                             INOUT name varchar(64) DEFAULT NULL,
                             INOUT description varchar(256) DEFAULT NULL,
                             INOUT decsize integer DEFAULT NULL,
                             INOUT encsize integer DEFAULT NULL)
LANGUAGE plpgsql
SET search_path = config
AS $fn$
#variable_conflict use_column
DECLARE
    p_nodeid integer := nodeid;
    r record;
BEGIN
    FOR r IN SELECT t.id, t.name, t.description, t.decsize, t.encsize
               FROM packets p INNER JOIN vartypes t ON p.vartypeid = t.id
              WHERE p.nodeid = p_nodeid
    LOOP
        vartypeid := r.id; name := r.name; description := r.description; decsize := r.decsize; encsize := r.encsize;
    END LOOP;
END
$fn$;

-- ---------------------------------------------------------------------------------------------------
-- dbo.spTestExport(@TestID)  (bridge: BridgeMonitor runs "EXEC spTestExport ..." -> "SELECT config.sptestexport(...)")
CREATE FUNCTION sptestexport(testid integer)
RETURNS void
LANGUAGE plpgsql
SET search_path = config
AS $fn$
#variable_conflict use_column
DECLARE
    p_testid integer := testid;
BEGIN
    INSERT INTO jobs(testid, packetid, intfid, done)
        SELECT p_testid AS id,
               p.id     AS packetid,
               p.nodeid AS intfid,
               false    AS done
          FROM actors       AS a
         INNER JOIN devices      AS d ON a.deviceid = d.id
         INNER JOIN treeversions AS n ON d.smartnodeid = n.id
         INNER JOIN treeversions AS i ON n.id = i.parentid
         INNER JOIN packets      AS p ON i.id = p.nodeid
         WHERE (a.testid = p_testid)
           AND (i.iconid IN (6, 7));
END
$fn$;

-- ---------------------------------------------------------------------------------------------------
-- dbo.spAddMapping / spDelMapping / spMoveField
CREATE FUNCTION spaddmapping(fieldid integer, connectionid integer)
RETURNS void
LANGUAGE plpgsql
SET search_path = config
AS $fn$
#variable_conflict use_column
DECLARE
    p_fieldid integer := fieldid;
    p_connectionid integer := connectionid;
BEGIN
    UPDATE fields SET connectionid = p_connectionid WHERE id = p_fieldid;
END
$fn$;

CREATE FUNCTION spdelmapping(fieldid integer, connectionid integer)   -- @ConnectionID is unused in the original too
RETURNS void
LANGUAGE plpgsql
SET search_path = config
AS $fn$
#variable_conflict use_column
DECLARE
    p_fieldid integer := fieldid;
BEGIN
    UPDATE fields SET connectionid = NULL WHERE id = p_fieldid;
END
$fn$;

CREATE FUNCTION spmovefield(fieldid integer, vartypeid integer)
RETURNS void
LANGUAGE plpgsql
SET search_path = config
AS $fn$
#variable_conflict use_column
DECLARE
    p_fieldid integer := fieldid;
    p_vartypeid integer := vartypeid;
BEGIN
    UPDATE fields SET vartypeid = p_vartypeid WHERE id = p_fieldid;
END
$fn$;

-- ---------------------------------------------------------------------------------------------------
-- dbo.spCleanTypes(@ScopeID) / dbo.spVarTypes(@ScopeID)  (SELECT * FROM VarTypes ...)
CREATE FUNCTION spcleantypes(scopeid integer)
RETURNS SETOF vartypes
LANGUAGE plpgsql
SET search_path = config
AS $fn$
#variable_conflict use_column
DECLARE
    p_scopeid integer := scopeid;
BEGIN
    RETURN QUERY SELECT * FROM vartypes WHERE scopeid = p_scopeid;
END
$fn$;

CREATE FUNCTION spvartypes(scopeid integer)
RETURNS SETOF vartypes
LANGUAGE plpgsql
SET search_path = config
AS $fn$
#variable_conflict use_column
DECLARE
    p_scopeid integer := scopeid;
BEGIN
    RETURN QUERY
        SELECT * FROM vartypes WHERE id < 100
        UNION ALL
        SELECT * FROM vartypes WHERE scopeid = p_scopeid;
END
$fn$;

-- ---------------------------------------------------------------------------------------------------
-- Tree operations: dbo.spDelete / spDeleteNode / spDeletePacket  (mutually recursive, as in T-SQL)
CREATE FUNCTION spdelete(nodeid integer)
RETURNS void
LANGUAGE plpgsql
SET search_path = config
AS $fn$
#variable_conflict use_column
DECLARE
    p_nodeid integer := nodeid;
    v_iconid integer;
BEGIN
    v_iconid := (SELECT iconid FROM treeversions WHERE id = p_nodeid);

    -- 2) Stage 3) Version 4) Release 5) Smart Node 6,7) Packet (Interface) 8) Hardware 9) Area 10) Board
    IF v_iconid IN (2, 3, 4, 5, 8, 9, 10) THEN
        PERFORM spdeletenode(p_nodeid);
    ELSIF v_iconid IN (6, 7) THEN
        PERFORM spdeletepacket(p_nodeid);
    END IF;

    DELETE FROM treeversions WHERE id = p_nodeid;
END
$fn$;

CREATE FUNCTION spdeletenode(nodeid integer)
RETURNS void
LANGUAGE plpgsql
SET search_path = config
AS $fn$
#variable_conflict use_column
DECLARE
    p_nodeid integer := nodeid;
    v_id integer;
BEGIN
    v_id := (SELECT MIN(id) FROM treeversions WHERE parentid = p_nodeid);
    WHILE v_id IS NOT NULL LOOP
        PERFORM spdelete(v_id);
        v_id := (SELECT MIN(id) FROM treeversions WHERE parentid = p_nodeid);
    END LOOP;
END
$fn$;

CREATE FUNCTION spdeletepacket(nodeid integer)
RETURNS void
LANGUAGE plpgsql
SET search_path = config
AS $fn$
#variable_conflict use_column
DECLARE
    p_nodeid integer := nodeid;
BEGIN
    DELETE FROM packets WHERE nodeid = p_nodeid;
    DELETE FROM vartypes WHERE scopeid = p_nodeid;   -- fields go with ON DELETE CASCADE (FK_Fields_VarTypes)
END
$fn$;

-- ---------------------------------------------------------------------------------------------------
-- Tree operations: dbo.spDuplicate and helpers
CREATE FUNCTION spduplicate(sourceid integer, targetid integer)
RETURNS void
LANGUAGE plpgsql
SET search_path = config
AS $fn$
#variable_conflict use_column
DECLARE
    p_sourceid integer := sourceid;
    p_targetid integer := targetid;
    v_iconid integer;
BEGIN
    v_iconid := (SELECT iconid FROM treeversions WHERE id = p_sourceid);

    IF v_iconid BETWEEN 2 AND 10 THEN
        PERFORM spduplicatenode(p_sourceid, p_targetid);
    END IF;

    IF v_iconid = 5 THEN
        PERFORM spduplicatemapping(p_sourceid, p_targetid);
    ELSIF v_iconid IN (6, 7) THEN
        PERFORM spduplicatepacket(p_sourceid, p_targetid);
    END IF;
    IF v_iconid = 10 THEN
        PERFORM spduplicateconnectors(p_sourceid, p_targetid);
    END IF;
END
$fn$;

CREATE FUNCTION spduplicateconnectors(sourceid integer, targetid integer)
RETURNS void
LANGUAGE plpgsql
SET search_path = config
AS $fn$
#variable_conflict use_column
DECLARE
    p_sourceid integer := sourceid;
    p_targetid integer := targetid;
BEGIN
    INSERT INTO connections(boardid, firstpin, linktypeid, connectorid, seq, description, shortname)
        SELECT p_targetid, firstpin, linktypeid, connectorid, seq, description, shortname
          FROM connections
         WHERE boardid = p_sourceid
         ORDER BY id;   -- deterministic identity order (T-SQL has none; SQL Server's plan reads by ID)
END
$fn$;

-- Note (kept from the original): @Count counts the source children with IconID 6/7, but the loop then walks the
-- first @Count children by ID without filtering on IconID.
CREATE FUNCTION spduplicatemapping(sourceid integer, targetid integer)
RETURNS void
LANGUAGE plpgsql
SET search_path = config
AS $fn$
#variable_conflict use_column
DECLARE
    p_sourceid integer := sourceid;
    p_targetid integer := targetid;
    v_count integer;
    v_interfaceid integer;
BEGIN
    v_count := (SELECT COUNT(*) FROM treeversions WHERE (parentid = p_sourceid) AND (iconid IN (6, 7)));
    v_interfaceid := 0;
    WHILE v_count > 0 LOOP
        v_count := v_count - 1;
        v_interfaceid := (SELECT MIN(id) FROM treeversions WHERE (parentid = p_sourceid) AND (id > v_interfaceid));

        -- #V = getvartypesintopologicalorder(v_interfaceid); #M = CTE m
        WITH m AS (
            SELECT f.id AS fieldid, a.name AS area, b.name AS board, c.firstpin
              FROM treeversions i
             INNER JOIN packets      p ON i.id        = p.nodeid
             INNER JOIN vartypes     r ON r.scopeid   = p.nodeid
             INNER JOIN getvartypesintopologicalorder(v_interfaceid) v ON r.id = v.vartypeid
             INNER JOIN fields       f ON f.vartypeid = r.id
             INNER JOIN connections  c ON c.id        = f.connectionid
             INNER JOIN treeversions b ON b.id        = c.boardid
             INNER JOIN treeversions a ON a.id        = b.parentid
             WHERE i.id = v_interfaceid
        )
        UPDATE fields AS trgf
           SET connectionid = c.id
          FROM fields       AS srcf
         INNER JOIN vartypes     AS srcr ON srcf.vartypeid = srcr.id
         INNER JOIN treeversions AS srci ON srcr.scopeid   = srci.id
         INNER JOIN treeversions AS srcn ON srci.parentid  = srcn.id AND srcn.id = p_sourceid
         INNER JOIN treeversions AS trgn ON trgn.id = p_targetid
         INNER JOIN treeversions AS trgi ON trgi.parentid  = trgn.id AND trgi.name = srci.name
         INNER JOIN vartypes     AS trgr ON trgr.scopeid   = trgi.id AND trgr.name = srcr.name
         INNER JOIN m                    ON m.fieldid      = srcf.id
         INNER JOIN treeversions AS trgh ON trgh.parentid  = trgn.id
         INNER JOIN treeversions AS trga ON trga.parentid  = trgh.id AND trga.name = m.area
         INNER JOIN treeversions AS trgb ON trgb.parentid  = trga.id AND trgb.name = m.board
         INNER JOIN connections  AS c    ON c.boardid      = trgb.id AND c.firstpin = m.firstpin
         WHERE trgf.vartypeid = trgr.id AND trgf.name = srcf.name;   -- (the T-SQL "INNER JOIN Fields AS TrgF ON ...")
    END LOOP;
END
$fn$;

CREATE FUNCTION spduplicatenode(sourceid integer, targetid integer)
RETURNS void
LANGUAGE plpgsql
SET search_path = config
AS $fn$
#variable_conflict use_column
DECLARE
    p_sourceid integer := sourceid;
    p_targetid integer := targetid;
    v_name   varchar(64);
    v_iconid integer;
    v_seq    integer;
    v_id     integer;
    v_count  integer;
    v_nodeid integer;
    r record;
BEGIN
    -- Make sure the nodes are duplicated
    FOR r IN SELECT CASE s.iconid
                        WHEN 2 THEN 'Stage'
                        WHEN 3 THEN 'Version'
                        WHEN 4 THEN 'Release'
                        WHEN 5 THEN 'Smart Node'
                        ELSE s.name
                    END AS name,
                    s.iconid,
                    CASE s.seq WHEN NULL THEN NULL ELSE s.seq + 1 END AS seq   -- (WHEN NULL never matches; kept as in T-SQL)
               FROM treeversions s
              WHERE s.id = p_sourceid
    LOOP
        v_name := r.name; v_iconid := r.iconid; v_seq := r.seq;
    END LOOP;

    UPDATE treeversions
       SET name   = v_name,
           iconid = v_iconid,
           seq    = v_seq
     WHERE id = p_targetid;

    -- Duplicate all children
    v_id := 0;
    v_count := (SELECT COUNT(*) FROM treeversions WHERE parentid = p_sourceid);
    WHILE v_count > 0 LOOP
        v_count := v_count - 1;
        v_id := (SELECT MIN(id) FROM treeversions WHERE (parentid = p_sourceid) AND (id > v_id));

        INSERT INTO treeversions(name, parentid) VALUES ('Node', p_targetid) RETURNING id INTO v_nodeid;   -- @@IDENTITY

        PERFORM spduplicate(v_id, v_nodeid);
    END LOOP;
END
$fn$;

-- Note (kept from the original): the UPDATE writes "Seq = Seq" (a no-op), not the incremented @Seq.
CREATE FUNCTION spduplicatepacket(sourceid integer, targetid integer)
RETURNS void
LANGUAGE plpgsql
SET search_path = config
AS $fn$
#variable_conflict use_column
DECLARE
    p_sourceid integer := sourceid;
    p_targetid integer := targetid;
    v_name     varchar(50);
    v_iconid   integer;
    v_seq      integer;
    v_srcisinput   boolean;
    v_srcvartypeid integer;
    v_trgvartypeid integer;
    v_packetid     integer;
    pair_src integer[];    -- #VarTypePairs.SourceVarTypeID
    pair_trg integer[];    -- #VarTypePairs.TargetVarTypeID
    r record;
BEGIN
    -- Just in case, make a copy of the source node in TreeVersions
    FOR r IN SELECT name, iconid, seq FROM treeversions WHERE id = p_sourceid LOOP
        v_name := r.name; v_iconid := r.iconid; v_seq := r.seq;
    END LOOP;

    IF v_seq IS NOT NULL THEN
        v_seq := v_seq + 1;
    END IF;

    UPDATE treeversions
       SET name   = v_name,
           iconid = v_iconid,
           seq    = seq
     WHERE id = p_targetid;

    -- Get the information about the original Packet (IsInput, VarType)
    FOR r IN SELECT isinput, vartypeid FROM packets WHERE nodeid = p_sourceid LOOP
        v_srcisinput := r.isinput; v_srcvartypeid := r.vartypeid;
    END LOOP;

    -- Create the new Packet and VarType
    INSERT INTO vartypes(name, scopeid) VALUES (v_name, p_targetid) RETURNING id INTO v_trgvartypeid;

    v_packetid := (SELECT MAX(id) FROM packets) + 1;
    INSERT INTO packets(id, isinput, vartypeid, nodeid) VALUES (v_packetid, v_srcisinput, v_trgvartypeid, p_targetid);

    pair_src := ARRAY[v_srcvartypeid];
    pair_trg := ARRAY[v_trgvartypeid];

    -- Copy all the VarTypes from Source to Target (cursor VarTypesCursor)
    FOR r IN SELECT id, name, description, shortname FROM vartypes WHERE scopeid = p_sourceid ORDER BY id LOOP
        -- IF NOT (@VarTypeID IN (SELECT SourceVarTypeID FROM #VarTypePairs))   (same NULL semantics)
        IF NOT (r.id = ANY (pair_src)) THEN
            INSERT INTO vartypes(name, scopeid, description, shortname)
                 VALUES (r.name, p_targetid, r.description, r.shortname)
              RETURNING id INTO v_trgvartypeid;
            pair_src := pair_src || r.id;
            pair_trg := pair_trg || v_trgvartypeid;
        END IF;
    END LOOP;

    -- Copy and translate all the fields (ConnectionID stays NULL on purpose)
    INSERT INTO fields(name, qty, typeid, seq, vartypeid, override, insequence, description, shortname, transformationid)
        SELECT f.name, f.qty, COALESCE(pt.trg, f.typeid) AS typeid, f.seq, po.trg, f.override, f.insequence,
               f.description, f.shortname, f.transformationid
          FROM fields f
         INNER JOIN unnest(pair_src, pair_trg) AS po(src, trg) ON f.vartypeid = po.src        -- Owner
          LEFT OUTER JOIN unnest(pair_src, pair_trg) AS pt(src, trg) ON f.typeid = pt.src     -- Type
         ORDER BY f.id;   -- T-SQL has no ORDER BY (identity order is plan-dependent); SQL Server's plan scans Fields by PK
END
$fn$;

-- ---------------------------------------------------------------------------------------------------
-- Device / interface / packet lookups (result-set procs)
-- The T-SQL input parameter @ID clashes with the result column ID (not allowed in PG): input renamed to deviceid.
CREATE FUNCTION spgetdevice(deviceid integer, testid integer)
RETURNS TABLE(id integer, name varchar(50), ipv4 varchar(15), port integer, smartnodeid integer)
LANGUAGE plpgsql
SET search_path = config
AS $fn$
#variable_conflict use_column
DECLARE
    p_id integer := deviceid;
    p_testid integer := testid;
BEGIN
    RETURN QUERY
    SELECT d.id, n.name, d.ipv4, d.port, d.smartnodeid
      FROM devices d
     INNER JOIN treeversions n ON d.smartnodeid = n.id
     INNER JOIN actors       a ON a.deviceid    = d.id
     WHERE (d.id = p_id) AND (a.testid = p_testid);
END
$fn$;

CREATE FUNCTION spgetdevices(testid integer)
RETURNS TABLE(deviceid integer)
LANGUAGE plpgsql
SET search_path = config
AS $fn$
#variable_conflict use_column
DECLARE
    p_testid integer := testid;
BEGIN
    RETURN QUERY
    SELECT d.deviceid FROM tests t INNER JOIN actors d ON t.id = d.testid WHERE t.id = p_testid;
END
$fn$;

CREATE FUNCTION spgethardwarenode(scopeid integer, INOUT nodeid integer DEFAULT NULL)
LANGUAGE plpgsql
SET search_path = config
AS $fn$
#variable_conflict use_column
DECLARE
    p_scopeid integer := scopeid;
    v_nodeid integer;
BEGIN
    v_nodeid := (SELECT id FROM treeversions WHERE parentid = p_scopeid AND iconid = 8);

    IF v_nodeid IS NULL THEN
        -- This hardware node was never created
        INSERT INTO treeversions(name, parentid, iconid) VALUES ('Hardware', p_scopeid, 8) RETURNING id INTO v_nodeid;
    END IF;
    nodeid := v_nodeid;
END
$fn$;

-- #T loop (add children with IconID 8/9/10 until no rows are added) == recursive CTE over the same rule.
CREATE FUNCTION spgethardwaretree(scopeid integer)
RETURNS TABLE(id integer, name varchar(50), parentid integer, iconid integer, seq integer)
LANGUAGE plpgsql
SET search_path = config
AS $fn$
#variable_conflict use_column
DECLARE
    p_scopeid integer := scopeid;
    v_nodeid integer;
BEGIN
    v_nodeid := (SELECT h.nodeid FROM spgethardwarenode(p_scopeid) h);

    RETURN QUERY
    WITH RECURSIVE t AS (
        SELECT tv.id, tv.name, tv.parentid, tv.iconid, tv.seq FROM treeversions tv WHERE tv.id = v_nodeid
        UNION
        SELECT c.id, c.name, c.parentid, c.iconid, c.seq
          FROM treeversions c INNER JOIN t ON c.parentid = t.id
         WHERE c.iconid IN (8, 9, 10)
    )
    SELECT t.id, t.name, t.parentid, t.iconid, t.seq FROM t
     ORDER BY t.parentid NULLS FIRST, t.seq NULLS FIRST, t.name NULLS FIRST;
END
$fn$;

CREATE FUNCTION spgetinppacketsizes()
RETURNS TABLE(packetid integer, name varchar(50), encsize integer)
LANGUAGE plpgsql
SET search_path = config
AS $fn$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT p.id AS packetid, t.name, t.encsize
      FROM treeversions AS i
     INNER JOIN packets  AS p ON i.id = p.nodeid
     INNER JOIN vartypes AS t ON p.vartypeid = t.id
     WHERE (i.iconid = 7) AND (t.encsize IS NOT NULL);
END
$fn$;

CREATE FUNCTION spgetinterface(nodeid integer)
RETURNS TABLE(varorder integer, recordname varchar(50), recorddescription varchar(128), fieldname varchar(50),
              arraylen integer, typename varchar(50), fielddescription varchar(128), override boolean, insequence boolean)
LANGUAGE plpgsql
SET search_path = config
AS $fn$
#variable_conflict use_column
DECLARE
    p_nodeid integer := nodeid;
BEGIN
    RETURN QUERY
    SELECT v.id AS varorder, r.name AS recordname, r.description AS recorddescription, f.name AS fieldname,
           f.qty AS arraylen, t.name AS typename, COALESCE(f.description, t.description) AS fielddescription,
           f.override, f.insequence
      FROM treeversions tree
     INNER JOIN packets  p ON tree.id     = p.nodeid
     INNER JOIN vartypes r ON r.scopeid   = p.nodeid
     INNER JOIN getvartypesintopologicalorder(p_nodeid) v ON r.id = v.vartypeid
     INNER JOIN fields   f ON f.vartypeid = r.id
     INNER JOIN vartypes t ON f.typeid    = t.id
     WHERE p.nodeid = p_nodeid
     ORDER BY v.id NULLS FIRST, r.name NULLS FIRST, f.seq NULLS FIRST, f.name NULLS FIRST;
END
$fn$;

CREATE FUNCTION spgetintf(id integer, testid integer)
RETURNS TABLE(packetid integer, name varchar(50), isinput boolean, intfid integer, smartnodeid integer, deviceid integer)
LANGUAGE plpgsql
SET search_path = config
AS $fn$
#variable_conflict use_column
DECLARE
    p_id integer := id;
    p_testid integer := testid;
BEGIN
    RETURN QUERY
    SELECT p.id AS packetid, v.name, p.isinput, p.nodeid AS intfid, n.id AS smartnodeid, d.id AS deviceid
      FROM packets p
     INNER JOIN treeversions i ON p.nodeid      = i.id
     INNER JOIN vartypes     v ON p.vartypeid   = v.id
     INNER JOIN treeversions n ON i.parentid    = n.id
     INNER JOIN devices      d ON d.smartnodeid = n.id
     INNER JOIN actors       a ON a.deviceid    = d.id
     WHERE (p.nodeid = p_id) AND (a.testid = p_testid);
END
$fn$;

CREATE FUNCTION spgetintfs(testid integer)
RETURNS TABLE(packetid integer, intfid integer, isinput boolean)
LANGUAGE plpgsql
SET search_path = config
AS $fn$
#variable_conflict use_column
DECLARE
    p_testid integer := testid;
BEGIN
    RETURN QUERY
    SELECT p.id AS packetid, p.nodeid AS intfid, p.isinput
      FROM actors AS a
     INNER JOIN devices      AS d ON a.deviceid = d.id
     INNER JOIN treeversions AS n ON d.smartnodeid = n.id
     INNER JOIN treeversions AS i ON n.id = i.parentid
     INNER JOIN packets      AS p ON i.id = p.nodeid
     WHERE (a.testid = p_testid) AND (i.iconid IN (6, 7));
END
$fn$;

-- ---------------------------------------------------------------------------------------------------
-- Mapping procs
CREATE FUNCTION spgetmappingbyconnection(connectionid integer, packetid integer,
                                         INOUT vartypeid integer DEFAULT NULL, INOUT fieldid integer DEFAULT NULL)
LANGUAGE plpgsql
SET search_path = config
AS $fn$
#variable_conflict use_column
DECLARE
    p_connectionid integer := connectionid;
    p_packetid integer := packetid;
    r record;
BEGIN
    vartypeid := NULL;
    fieldid   := NULL;
    FOR r IN SELECT t.id AS tid, f.id AS fid
               FROM vartypes AS t INNER JOIN fields AS f ON t.id = f.vartypeid
              WHERE (f.connectionid = p_connectionid) AND (t.scopeid = p_packetid)
    LOOP
        vartypeid := r.tid; fieldid := r.fid;
    END LOOP;
END
$fn$;

CREATE FUNCTION spgetmappingbyfield(fieldid integer, packetid integer,
                                    INOUT boardid integer DEFAULT NULL, INOUT connectionid integer DEFAULT NULL)
LANGUAGE plpgsql
SET search_path = config
AS $fn$
#variable_conflict use_column
DECLARE
    p_fieldid integer := fieldid;
    p_packetid integer := packetid;
    r record;
BEGIN
    FOR r IN SELECT c.boardid AS bid, f.connectionid AS cid
               FROM treeversions AS i
              INNER JOIN vartypes     AS r ON i.id = r.scopeid
              INNER JOIN fields       AS f ON r.id = f.vartypeid
              INNER JOIN treeversions AS h ON i.parentid = h.parentid
              INNER JOIN treeversions AS a ON h.id = a.parentid
              INNER JOIN treeversions AS b ON a.id = b.parentid
              INNER JOIN connections  AS c ON f.connectionid = c.id AND b.id = c.boardid
              WHERE (i.id = p_packetid) AND (f.id = p_fieldid)
    LOOP
        boardid := r.bid; connectionid := r.cid;
    END LOOP;
END
$fn$;

CREATE FUNCTION spgetmappingsortedbyconnections(nodeid integer)
RETURNS TABLE(id integer, connectionid integer)
LANGUAGE plpgsql
SET search_path = config
AS $fn$
#variable_conflict use_column
DECLARE
    p_nodeid integer := nodeid;
BEGIN
    RETURN QUERY
    SELECT (row_number() OVER (ORDER BY a.seq NULLS FIRST, a.name NULLS FIRST, b.name NULLS FIRST, b.seq NULLS FIRST,
                                        c.firstpin NULLS FIRST, t.name NULLS FIRST, f.seq NULLS FIRST, f.name NULLS FIRST))::integer AS id,
           m.connectionid
      FROM mappings     AS m
     INNER JOIN connections  AS c ON m.connectionid = c.id
     INNER JOIN treeversions AS b ON c.boardid = b.id
     INNER JOIN treeversions AS a ON b.parentid = a.id
     INNER JOIN treeversions AS h ON a.parentid = h.id
     INNER JOIN treeversions AS i ON h.parentid = i.parentid
     INNER JOIN vartypes     AS t ON i.id = t.scopeid
     INNER JOIN fields       AS f ON m.fieldid = f.id AND t.id = f.vartypeid
     WHERE i.id = p_nodeid
     ORDER BY 1;
END
$fn$;

CREATE FUNCTION spgetmappingsortedbyfields(nodeid integer)
RETURNS TABLE(id integer, fieldid integer)
LANGUAGE plpgsql
SET search_path = config
AS $fn$
#variable_conflict use_column
DECLARE
    p_nodeid integer := nodeid;
BEGIN
    RETURN QUERY
    SELECT (row_number() OVER (ORDER BY v.id NULLS FIRST, r.name NULLS FIRST, f.seq NULLS FIRST, f.name NULLS FIRST))::integer AS id,
           f.id AS fieldid
      FROM treeversions tree
     INNER JOIN packets  p ON tree.id     = p.nodeid
     INNER JOIN vartypes r ON r.scopeid   = p.nodeid
     INNER JOIN getvartypesintopologicalorder(p_nodeid) v ON r.id = v.vartypeid
     INNER JOIN fields   f ON f.vartypeid = r.id
     INNER JOIN vartypes t ON f.typeid    = t.id
     WHERE p.nodeid = p_nodeid
     ORDER BY 1;
END
$fn$;

CREATE FUNCTION spgetmappingwithorders(nodeid integer)
RETURNS TABLE(fieldid integer, connectionid integer, fieldorder integer, connectionorder integer, area varchar(50),
              board varchar(50), firstpin integer, interface varchar(50), record varchar(50), qty integer,
              field varchar(50), shortname varchar(16), description varchar(128))
LANGUAGE plpgsql
SET search_path = config
AS $fn$
#variable_conflict use_column
DECLARE
    p_nodeid integer := nodeid;
BEGIN
    RETURN QUERY
    WITH ff AS (   -- #F
        SELECT (row_number() OVER (ORDER BY v.id NULLS FIRST, r.name NULLS FIRST, f.seq NULLS FIRST, f.name NULLS FIRST))::integer AS id,
               f.id AS fieldid
          FROM treeversions i
         INNER JOIN packets  p ON i.id = p.nodeid
         INNER JOIN vartypes r ON r.scopeid = p.nodeid
         INNER JOIN getvartypesintopologicalorder(p_nodeid) v ON r.id = v.vartypeid
         INNER JOIN fields   f ON f.vartypeid = r.id
         INNER JOIN vartypes t ON f.typeid = t.id
         WHERE p.nodeid = p_nodeid
    ), cc AS (     -- #C
        SELECT (row_number() OVER (ORDER BY a.seq NULLS FIRST, a.name NULLS FIRST, b.name NULLS FIRST, b.seq NULLS FIRST,
                                            c.firstpin NULLS FIRST, t.name NULLS FIRST, f.seq NULLS FIRST, f.name NULLS FIRST))::integer AS id,
               f.connectionid
          FROM fields AS f
         INNER JOIN connections  AS c ON f.connectionid = c.id
         INNER JOIN treeversions AS b ON c.boardid = b.id
         INNER JOIN treeversions AS a ON b.parentid = a.id
         INNER JOIN treeversions AS h ON a.parentid = h.id
         INNER JOIN treeversions AS n ON h.parentid = n.id
         INNER JOIN treeversions AS i ON i.parentid = n.id
         INNER JOIN vartypes     AS t ON t.scopeid = i.id AND t.id = f.vartypeid
         WHERE (i.id = p_nodeid) AND (f.connectionid IS NOT NULL)
    )
    SELECT f.id AS fieldid, f.connectionid, ff.id AS fieldorder, cc.id AS connectionorder, a.name AS area, b.name AS board,
           c.firstpin, i.name AS interface, t.name AS record, r.qty, f.name AS field, c.shortname, c.description
      FROM connections  AS c
     INNER JOIN treeversions AS b ON c.boardid  = b.id
     INNER JOIN treeversions AS a ON b.parentid = a.id
     INNER JOIN treeversions AS h ON a.parentid = h.id
     INNER JOIN treeversions AS n ON h.parentid = n.id
     INNER JOIN treeversions AS i ON i.parentid = n.id
     INNER JOIN vartypes     AS t ON i.id = t.scopeid
     INNER JOIN fields       AS r ON t.id = r.typeid
     INNER JOIN fields       AS f ON t.id = f.vartypeid
     INNER JOIN ff                ON f.id = ff.fieldid
     INNER JOIN cc                ON f.connectionid = cc.connectionid AND f.connectionid = c.id
     WHERE (i.id = p_nodeid) AND (f.connectionid IS NOT NULL)
     ORDER BY cc.id NULLS FIRST;
END
$fn$;

CREATE FUNCTION spmappingexists(fieldid integer, connectionid integer, INOUT "exists" boolean DEFAULT NULL)
LANGUAGE plpgsql
SET search_path = config
AS $fn$
#variable_conflict use_column
DECLARE
    p_fieldid integer := fieldid;
    p_connectionid integer := connectionid;
    v_id integer;
BEGIN
    v_id := (SELECT connectionid FROM fields WHERE id = p_fieldid);
    "exists" := CASE WHEN v_id = p_connectionid THEN true ELSE false END;
END
$fn$;

-- ---------------------------------------------------------------------------------------------------
-- Node / packet lookups with OUTPUT parameters
CREATE FUNCTION spgetnodebypacket(packetid integer, testid integer, INOUT nodeid integer DEFAULT NULL)
LANGUAGE plpgsql
SET search_path = config
AS $fn$
#variable_conflict use_column
DECLARE
    p_packetid integer := packetid;
    p_testid integer := testid;
BEGIN
    nodeid := (SELECT p.nodeid
                 FROM packets p
                INNER JOIN treeversions i ON p.nodeid      = i.id
                INNER JOIN vartypes     v ON p.vartypeid   = v.id
                INNER JOIN treeversions n ON i.parentid    = n.id
                INNER JOIN devices      d ON d.smartnodeid = n.id
                INNER JOIN actors       a ON a.deviceid    = d.id
                WHERE (p.id = p_packetid) AND (a.testid = p_testid));
END
$fn$;

CREATE FUNCTION spgetnodeid(stage varchar(64), node varchar(64), packet varchar(64), INOUT nodeid integer DEFAULT NULL)
LANGUAGE plpgsql
SET search_path = config
AS $fn$
#variable_conflict use_column
DECLARE
    p_stage  varchar(64) := stage;
    p_node   varchar(64) := node;
    p_packet varchar(64) := packet;
    r record;
BEGIN
    FOR r IN SELECT i.id
               FROM treeversions AS s
              INNER JOIN treeversions AS v ON s.id = v.parentid
              INNER JOIN treeversions AS r ON v.id = r.parentid
              INNER JOIN treeversions AS n ON r.id = n.parentid
              INNER JOIN treeversions AS i ON n.id = i.parentid
              WHERE (s.name = p_stage) AND (n.name = p_node) AND (i.name = p_packet) AND (n.iconid = 5)
              ORDER BY v.name DESC NULLS LAST, r.name DESC NULLS LAST
              LIMIT 1                                                           -- TOP(1)
    LOOP
        nodeid := r.id;
    END LOOP;
END
$fn$;

CREATE FUNCTION spgetpacket(nodeid integer, INOUT packetid integer DEFAULT NULL,
                            INOUT packetname varchar(50) DEFAULT NULL, INOUT isinput boolean DEFAULT NULL)
LANGUAGE plpgsql
SET search_path = config
AS $fn$
#variable_conflict use_column
DECLARE
    p_nodeid integer := nodeid;
    r record;
BEGIN
    FOR r IN SELECT p.id, v.name, p.isinput
               FROM packets p INNER JOIN vartypes v ON p.vartypeid = v.id
              WHERE p.nodeid = p_nodeid
    LOOP
        packetid := r.id; packetname := r.name; isinput := r.isinput;
    END LOOP;
END
$fn$;

-- SELECT * FROM Servers s INNER JOIN Tests t ...: the T-SQL result set has two columns called ID and two called
-- Name; a PG function result cannot, so the Tests columns that clash are returned as id_1 / name_1 (the names
-- FireDAC itself gives the duplicates).
CREATE FUNCTION spgetserver(testid integer)
RETURNS TABLE(id integer, name varchar(50), winname varchar(64), fullname varchar(128), ipv4 varchar(15), port integer,
              opcservername varchar(128), sqlserverinstance varchar(128), databasename varchar(64), username varchar(64),
              password varchar(64), id_1 integer, name_1 varchar(64), description varchar(256), serverid integer,
              active boolean, started timestamp(3), stopped timestamp(3), export boolean)
LANGUAGE plpgsql
SET search_path = config
AS $fn$
#variable_conflict use_column
DECLARE
    p_testid integer := testid;
BEGIN
    RETURN QUERY
    SELECT s.id, s.name, s.winname, s.fullname, s.ipv4, s.port, s.opcservername, s.sqlserverinstance, s.databasename,
           s.username, s.password, t.id, t.name, t.description, t.serverid, t.active, t.started, t.stopped, t.export
      FROM servers s INNER JOIN tests t ON s.id = t.serverid
     WHERE t.id = p_testid;
END
$fn$;

CREATE FUNCTION spgetvartypefields(vartypeid integer)
RETURNS TABLE(fieldname varchar(50), arraylen integer, typeid integer, initialvalue varchar(128), typename varchar(50),
              fielddescription varchar(128), override boolean, insequence boolean, transformationid integer)
LANGUAGE plpgsql
SET search_path = config
AS $fn$
#variable_conflict use_column
DECLARE
    p_vartypeid integer := vartypeid;
BEGIN
    RETURN QUERY
    SELECT f.name AS fieldname, f.qty AS arraylen, f.typeid, f.initialvalue, t.name AS typename,
           COALESCE(f.description, t.description) AS fielddescription, f.override, f.insequence, f.transformationid
      FROM fields f INNER JOIN vartypes t ON f.typeid = t.id
     WHERE f.vartypeid = p_vartypeid
     ORDER BY f.seq NULLS FIRST, f.name NULLS FIRST;
END
$fn$;

-- ---------------------------------------------------------------------------------------------------
-- dbo.spLoadPacketDef
-- Note (kept from the original): the final INSERT INTO Packets(IsInput, VarTypeID, NodeID) does not supply
-- Packets.ID, which is NOT NULL without default/identity, so it fails in SQL Server as well. In T-SQL that
-- statement error leaves the earlier inserts committed (no transaction); in PG the whole call rolls back.
CREATE FUNCTION sploadpacketdef(nodeid integer, name varchar(50), isinput boolean, interfacename varchar(50))
RETURNS void
LANGUAGE plpgsql
SET search_path = config
AS $fn$
#variable_conflict use_column
DECLARE
    p_nodeid integer := nodeid;
    p_name varchar(50) := name;
    p_isinput boolean := isinput;
    p_interfacename varchar(50) := interfacename;
    v_iconid integer;
    v_packetid integer;
    v_vartypeid integer;
    v_grouptypeid integer;
    g record;
BEGIN
    -- Define the icon for the packet in the tree according to IsInput
    IF p_isinput = true THEN
        v_iconid := 6;
    ELSE
        v_iconid := 7;
    END IF;

    -- Create the new Packet in TreeVersions
    v_packetid := (SELECT id FROM treeversions WHERE parentid = p_nodeid AND name = p_name);
    IF v_packetid IS NULL THEN
        INSERT INTO treeversions(name, parentid, iconid) VALUES (p_name, p_nodeid, v_iconid) RETURNING id INTO v_packetid;
    END IF;

    -- Create the VarTypes
    v_vartypeid := (SELECT id FROM vartypes WHERE scopeid = v_packetid AND name = p_name);
    IF v_vartypeid IS NULL THEN
        INSERT INTO vartypes(name, scopeid) VALUES (p_name, v_packetid) RETURNING id INTO v_vartypeid;
    END IF;

    -- Add to the packet VarType all the global variables (like t_ms)
    IF NOT EXISTS (SELECT * FROM fields WHERE vartypeid = v_vartypeid) THEN
        INSERT INTO fields(name, qty, typeid, vartypeid)
            SELECT i.varname AS name, i.arraylen AS qty, t.id AS typeid, v_vartypeid AS vartypeid
              FROM viewinterfaces AS i INNER JOIN vartypes t ON i.data_type = t.name
             WHERE i.groupname IS NULL AND i.interfacename = p_interfacename
             ORDER BY i.varname;
    END IF;

    -- Define all the types used by the packet (GroupCursor)
    FOR g IN SELECT groupname, qty
               FROM viewgroups
              WHERE groupname IS NOT NULL AND interfacename = p_interfacename
              ORDER BY grouporder NULLS FIRST
    LOOP
        INSERT INTO vartypes(name, scopeid) VALUES (g.groupname, v_packetid) RETURNING id INTO v_grouptypeid;

        INSERT INTO fields(name, qty, typeid, vartypeid)
            SELECT i.varname AS name, i.arraylen AS qty, t.id AS typeid, v_grouptypeid AS vartypeid
              FROM viewinterfaces AS i INNER JOIN vartypes t ON i.data_type = t.name
             WHERE i.groupname = g.groupname AND i.interfacename = p_interfacename
             ORDER BY i.varname;

        INSERT INTO fields(name, qty, typeid, vartypeid) VALUES (g.groupname, g.qty, v_grouptypeid, v_vartypeid);
    END LOOP;

    -- Insert the final packet
    INSERT INTO packets(isinput, vartypeid, nodeid) VALUES (p_isinput, v_vartypeid, p_nodeid);
END
$fn$;

-- ---------------------------------------------------------------------------------------------------
-- dbo.spMoveNodeToSeq(@NodeID, @Seq)   (#S IDENTITY ordering -> row_number)
CREATE FUNCTION spmovenodetoseq(nodeid integer, seq integer)
RETURNS void
LANGUAGE plpgsql
SET search_path = config
AS $fn$
#variable_conflict use_column
DECLARE
    p_nodeid integer := nodeid;
    p_seq integer := seq;
    v_parentid integer;
BEGIN
    v_parentid := (SELECT parentid FROM treeversions WHERE id = p_nodeid);

    WITH s AS (
        SELECT tv.id, tv.seq, row_number() OVER (ORDER BY tv.seq NULLS FIRST, tv.name NULLS FIRST) AS i
          FROM treeversions tv
         WHERE (tv.parentid = v_parentid) AND (tv.id <> p_nodeid)
    ), s2 AS (
        SELECT s.id,
               CASE WHEN s.i <  p_seq THEN s.i          -- UPDATE #S SET Seq = I     WHERE I <  @Seq
                    WHEN s.i >= p_seq THEN s.i + 1      -- UPDATE #S SET Seq = I + 1 WHERE I >= @Seq
                    ELSE s.seq                          -- @Seq NULL: neither UPDATE touches the row
               END AS seq
          FROM s
        UNION ALL
        SELECT p_nodeid, p_seq                          -- INSERT INTO #S(ID, Seq) VALUES(@NodeID, @Seq)
    )
    UPDATE treeversions t
       SET seq = s2.seq * 20
      FROM s2
     WHERE t.id = s2.id;
END
$fn$;

-- ---------------------------------------------------------------------------------------------------
-- dbo.spPopulateTreeVersions  (initial tree + base types; SET IDENTITY_INSERT -> explicit ids + identity_insert_bump)
-- Note: T-SQL continues after the (expected) spLoadPacketDef error; PG aborts the call at the first error.
CREATE FUNCTION sppopulatetreeversions()
RETURNS void
LANGUAGE plpgsql
SET search_path = config
AS $fn$
#variable_conflict use_column
DECLARE
    v_nodeid integer;
BEGIN
    IF (SELECT COUNT(*) FROM treeversions) = 0 THEN
        INSERT INTO treeversions(id, name, parentid, iconid) VALUES (1, 'Vehicle', NULL, 1);
        INSERT INTO treeversions(id, name, parentid, iconid) VALUES (2, 'Stage 1', 1, 2);
        INSERT INTO treeversions(id, name, parentid, iconid) VALUES (3, 'Version 0', 2, 3);
        INSERT INTO treeversions(id, name, parentid, iconid) VALUES (4, 'Release 0.1', 3, 4);
        PERFORM identity_insert_bump('config.treeversions', 'id', 4);
    END IF;

    IF (SELECT COUNT(*) FROM vartypes) = 0 THEN
        INSERT INTO vartypes(id, name, scopeid) VALUES (1 , 'bool'  , 1);
        INSERT INTO vartypes(id, name, scopeid) VALUES (2 , 'u8'    , 1);
        INSERT INTO vartypes(id, name, scopeid) VALUES (3 , 'u12'   , 1);
        INSERT INTO vartypes(id, name, scopeid) VALUES (4 , 'u16'   , 1);
        INSERT INTO vartypes(id, name, scopeid) VALUES (5 , 'u32'   , 1);
        INSERT INTO vartypes(id, name, scopeid) VALUES (6 , 'i8'    , 1);
        INSERT INTO vartypes(id, name, scopeid) VALUES (7 , 'i16'   , 1);
        INSERT INTO vartypes(id, name, scopeid) VALUES (8 , 'i32'   , 1);
        INSERT INTO vartypes(id, name, scopeid) VALUES (9 , 'f32'   , 1);
        INSERT INTO vartypes(id, name, scopeid) VALUES (10, 'f64'   , 1);
        INSERT INTO vartypes(id, name, scopeid) VALUES (11, 'i32q8' , 1);
        INSERT INTO vartypes(id, name, scopeid) VALUES (12, 'i32q16', 1);
        INSERT INTO vartypes(id, name, scopeid) VALUES (13, 'u8q8'  , 1);
        INSERT INTO vartypes(id, name, scopeid) VALUES (14, 'u16q16', 1);
        -- Let's try to reserve types lower than 100 for future use
        INSERT INTO vartypes(id, name, scopeid) VALUES (99, 'dummy', 1);
        PERFORM identity_insert_bump('config.vartypes', 'id', 99);
        DELETE FROM vartypes WHERE id = 99;
    END IF;

    v_nodeid := (SELECT id FROM treeversions WHERE name = 'eMaster');
    IF v_nodeid IS NULL THEN
        INSERT INTO treeversions(name, parentid, iconid) VALUES ('eMaster', 4, 5) RETURNING id INTO v_nodeid;
    END IF;

    PERFORM sploadpacketdef(v_nodeid, 'L2R', true, 'A1S1Tester1_l2r');
    PERFORM sploadpacketdef(v_nodeid, 'R2L', false, 'A1S1Tester1_r2l');
    PERFORM sploadpacketdef(v_nodeid, 'EngineL2R', true, 'A1S1EngineTester1_l2r');
    PERFORM sploadpacketdef(v_nodeid, 'EngineR2L', false, 'A1S1EngineTester1_r2l');
END
$fn$;

-- ---------------------------------------------------------------------------------------------------
-- dbo.spSetPacket
CREATE FUNCTION spsetpacket(nodeid integer, packetid integer, packetname varchar(50), isinput boolean)
RETURNS void
LANGUAGE plpgsql
SET search_path = config
AS $fn$
#variable_conflict use_column
DECLARE
    p_nodeid integer := nodeid;
    p_packetid integer := packetid;
    p_packetname varchar(50) := packetname;
    p_isinput boolean := isinput;
    v_vartypeid integer;
BEGIN
    IF EXISTS (SELECT * FROM packets WHERE nodeid = p_nodeid) THEN
        -- Update Packet and VarType
        UPDATE packets SET id = p_packetid, isinput = p_isinput WHERE nodeid = p_nodeid;

        v_vartypeid := (SELECT vartypeid FROM packets WHERE nodeid = p_nodeid);
        IF v_vartypeid IS NULL THEN
            INSERT INTO vartypes(name, scopeid) VALUES (p_packetname, p_nodeid) RETURNING id INTO v_vartypeid;
            UPDATE packets SET vartypeid = v_vartypeid WHERE nodeid = p_nodeid;
        ELSE
            UPDATE vartypes SET name = p_packetname WHERE id = v_vartypeid;
        END IF;
    ELSE
        -- Create the packet and VarType
        INSERT INTO vartypes(name, scopeid) VALUES (p_packetname, p_nodeid) RETURNING id INTO v_vartypeid;
        INSERT INTO packets(id, isinput, vartypeid, nodeid) VALUES (p_packetid, p_isinput, v_vartypeid, p_nodeid);
    END IF;
END
$fn$;

-- ---------------------------------------------------------------------------------------------------
-- Test lifecycle
CREATE FUNCTION sptestinterfaces(atestid integer)
RETURNS TABLE(smartnodename varchar(50), ipv4 varchar(15), port integer, interfacename varchar(50), isinput boolean, libraryname text)
LANGUAGE plpgsql
SET search_path = config
AS $fn$
#variable_conflict use_column
DECLARE
    p_atestid integer := atestid;
BEGIN
    RETURN QUERY
    SELECT n.name AS smartnodename, d.ipv4, d.port, i.name AS interfacename, p.isinput,
           ('\\' || s.fullname || '\' || v.name || '\')::text AS libraryname
      FROM actors AS a
     INNER JOIN devices      AS d ON a.deviceid    = d.id
     INNER JOIN treeversions AS n ON d.smartnodeid = n.id
     INNER JOIN treeversions AS i ON n.id          = i.parentid
     INNER JOIN packets      AS p ON i.id          = p.nodeid
     INNER JOIN vartypes     AS v ON p.vartypeid   = v.id
     INNER JOIN tests        AS t ON a.testid      = t.id
     INNER JOIN servers      AS s ON t.serverid    = s.id
     WHERE t.id = p_atestid;
END
$fn$;


CREATE FUNCTION spteststart(testid integer)
RETURNS void
LANGUAGE plpgsql
SET search_path = config
AS $fn$
#variable_conflict use_column
DECLARE
    p_testid integer := testid;
BEGIN
    UPDATE tests SET active = true, started = LOCALTIMESTAMP WHERE id = p_testid;          -- getdate()
END
$fn$;

CREATE FUNCTION spteststop(testid integer)
RETURNS void
LANGUAGE plpgsql
SET search_path = config
AS $fn$
#variable_conflict use_column
DECLARE
    p_testid integer := testid;
BEGIN
    UPDATE tests SET active = false, stopped = LOCALTIMESTAMP + interval '1 second' WHERE id = p_testid;   -- dateadd(second, 1, getdate())
END
$fn$;

-- ---------------------------------------------------------------------------------------------------
-- Trigger dbo.trgAfterDeleteOnConnections  (AFTER DELETE, statement level; "deleted" -> transition table)
-- Same caveat in both engines: FK_Fields_Connections (NO ACTION) is checked before this AFTER trigger runs, so a
-- delete of a Connection that is still referenced by Fields fails with an FK error and the trigger never gets to
-- clear Fields.ConnectionID.
CREATE FUNCTION trgafterdeleteonconnections()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = config
AS $fn$
BEGIN
    UPDATE fields f
       SET connectionid = NULL
      FROM deleted c
     WHERE f.connectionid = c.id;
    RETURN NULL;
END
$fn$;

CREATE TRIGGER trgafterdeleteonconnections
    AFTER DELETE ON connections
    REFERENCING OLD TABLE AS deleted
    FOR EACH STATEMENT
    EXECUTE FUNCTION trgafterdeleteonconnections();
-- =====================================================================
-- SCHEMA testlog  (from AstraTestLog.dbo)
-- =====================================================================
-- Both procedures import NI logger data (NI Citadel / "NIVariable_Default" database, tables NI_VARIABLE_NUMERIC and
-- NI_VARIABLE_BOOLEAN) into the per-test wide tables testlog.<Table>_<TestName>. That NI database is NOT part of
-- the backups, so these functions compile but cannot run until its tables are reachable from this PG database as
-- nivariable_default.ni_variable_numeric / nivariable_default.ni_variable_boolean (columns traceurl, "timestamp",
-- value), e.g. migrated into a schema of that name or mapped with postgres_fdw.
-- Translation notes:
--   * T-SQL LIKE is case-insensitive here (CI collation) and has no escape character, so "'%' + @x + '\%'"
--     becomes  ILIKE '%' || x || '\%' ESCAPE ''  (PG LIKE would otherwise treat backslash as an escape).
--   * charindex (case-insensitive) -> strpos(lower(..), lower(..));  len -> length.
--   * sys.columns/sys.types lookup -> information_schema.columns ('bit' -> 'boolean', 'float' -> 'double precision').
--   * EXEC(@sql) string building -> EXECUTE format(...) with %I / %L quoting (same statements for valid input,
--     but table/column names and the traceurl literal are now quoted instead of pasted raw).
--   * CONVERT(int, d.value) truncates toward zero -> trunc(d.value)::integer (a plain ::integer would round).
--   * Table names are folded to lower case (testlog tables are lower case in PG).

CREATE FUNCTION testlog.spimportvalues(tablename varchar(64), testname varchar(8))
RETURNS void
LANGUAGE plpgsql
SET search_path = testlog, config
AS $fn$
#variable_conflict use_column
DECLARE
    p_tablename  varchar(64) := tablename;
    p_testname   varchar(8)  := testname;
    v_table      varchar(72);
    v_testid     integer;
    v_traceurl   varchar(128);
    v_fieldname  varchar(64);
    v_fieldtype  text;
    v_fieldvalue text;
    v_vartable   varchar(32);
BEGIN
    v_table  := p_tablename || '_' || p_testname;
    v_testid := p_testname::integer;                       -- CONVERT(int, @TestName)

    FOR v_traceurl IN
        SELECT DISTINCT n.traceurl
          FROM nivariable_default.ni_variable_numeric n, config.tests t
         WHERE (n.traceurl ILIKE '%' || p_tablename || '\%' ESCAPE '') AND (t.id = v_testid)
           AND (n."timestamp" BETWEEN t.started AND t.stopped)
        UNION
        SELECT DISTINCT b.traceurl
          FROM nivariable_default.ni_variable_boolean b, config.tests t
         WHERE (b.traceurl ILIKE '%' || p_tablename || '\%' ESCAPE '') AND (t.id = v_testid)
           AND (b."timestamp" BETWEEN t.started AND t.stopped)
    LOOP
        v_fieldname := right(v_traceurl, length(v_traceurl) - strpos(lower(v_traceurl), lower(p_tablename)) - 3);
        v_fieldtype := (SELECT c.data_type
                          FROM information_schema.columns c
                         WHERE c.table_schema = 'testlog' AND c.table_name = lower(v_table)
                           AND c.column_name = lower(v_fieldname));

        IF v_fieldtype = 'boolean' THEN                     -- 'bit'
            v_vartable   := 'ni_variable_boolean';
            v_fieldvalue := 'd.value';
        ELSIF v_fieldtype = 'double precision' THEN         -- 'float'
            v_vartable   := 'ni_variable_numeric';
            v_fieldvalue := 'd.value';
        ELSE
            v_vartable   := 'ni_variable_numeric';
            v_fieldvalue := 'trunc(d.value)::integer';      -- CONVERT(int, d.value)
        END IF;

        EXECUTE format(
            'WITH data("timestamp", value) AS ('
            '    SELECT "timestamp", value FROM nivariable_default.%I WHERE traceurl = %L'
            '), newdata("timestamp", value) AS ('
            '    SELECT (SELECT max("timestamp") FROM testlog.%I WHERE "timestamp" <= data."timestamp") AS "timestamp", value'
            '      FROM data'
            ') '
            'UPDATE testlog.%I AS t SET %I = %s FROM newdata d WHERE t."timestamp" = d."timestamp"',
            v_vartable, v_traceurl, lower(v_table), lower(v_table), lower(v_fieldname), v_fieldvalue);
    END LOOP;
END
$fn$;

CREATE FUNCTION testlog.spinserttimestamps(tablename varchar(64), testname varchar(8))
RETURNS void
LANGUAGE plpgsql
SET search_path = testlog, config
AS $fn$
#variable_conflict use_column
DECLARE
    p_tablename varchar(64) := tablename;
    p_testname  varchar(8)  := testname;
    v_table     varchar(72);
    v_field     varchar(64);
    v_pattern   text;
BEGIN
    v_table := p_tablename || '_' || p_testname;
    IF EXISTS (SELECT * FROM information_schema.columns c
                WHERE c.table_schema = 'testlog' AND c.table_name = lower(v_table) AND c.column_name = 't_ms') THEN
        v_field := 't_ms';
    ELSE
        v_field := '';
    END IF;

    EXECUTE format('TRUNCATE TABLE testlog.%I', lower(v_table));

    v_pattern := '%' || p_tablename || '\' || v_field || '%';
    EXECUTE format(
        'WITH t1("timestamp") AS ('
        '    SELECT DISTINCT b."timestamp" FROM nivariable_default.ni_variable_boolean b, config.tests t'
        '     WHERE (b.traceurl ILIKE %1$L ESCAPE '''') AND (t.id = %2$s) AND (b."timestamp" BETWEEN t.started AND t.stopped)'
        '), t2("timestamp") AS ('
        '    SELECT DISTINCT n."timestamp" FROM nivariable_default.ni_variable_numeric n, config.tests t'
        '     WHERE (n.traceurl ILIKE %1$L ESCAPE '''') AND (t.id = %2$s) AND (n."timestamp" BETWEEN t.started AND t.stopped)'
        '), t("timestamp") AS ('
        '    SELECT "timestamp" FROM t1 UNION SELECT "timestamp" FROM t2'
        ') '
        'INSERT INTO testlog.%3$I ("timestamp") SELECT DISTINCT "timestamp" FROM t ORDER BY "timestamp"',
        v_pattern, p_testname::integer, lower(v_table));
END
$fn$;

RESET search_path;
-- Suggested for applications (Delphi SQL with unqualified names):
--   ALTER DATABASE <yourdb> SET search_path = config, testlog, public;
