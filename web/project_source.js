import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

app.registerExtension({
    name: "json.manager.project.source",

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name !== "ProjectSource") return;

        // Helper: replace a STRING widget with a proper combo widget
        function replaceWithCombo(node, name, values, callback) {
            const idx = node.widgets?.findIndex(w => w.name === name);
            if (idx === -1 || idx === undefined) return null;
            const oldWidget = node.widgets[idx];
            const savedValue = oldWidget.value || "";
            const comboValues = values.length > 0 ? values : [""];
            // Always preserve saved value (may not be in list yet)
            if (savedValue && !comboValues.includes(savedValue)) {
                comboValues.unshift(savedValue);
            }
            const defaultValue = savedValue || comboValues[0];
            node.widgets.splice(idx, 1);
            const combo = node.addWidget("combo", name, defaultValue, callback, { values: comboValues });
            if (node.widgets.length > 1) {
                node.widgets.splice(node.widgets.length - 1, 1);
                node.widgets.splice(idx, 0, combo);
            }
            return combo;
        }

        // Fetch active project from Manager and update project_name + title
        async function refreshActiveProject(node) {
            const urlW = node.widgets?.find(w => w.name === "manager_url");
            if (!urlW?.value) return;
            try {
                const resp = await fetch(`${urlW.value}/api/active-project`);
                if (!resp.ok) return;
                const data = await resp.json();
                const project = data.project || "";
                const projW = node.widgets?.find(w => w.name === "project_name");
                if (projW && projW.value !== project) {
                    projW.value = project;
                    await refreshFiles(node);
                }
                _updateTitle(node);
            } catch (e) {
                console.warn("[ProjectSource] Failed to fetch active project:", e);
            }
        }

        function _updateTitle(node) {
            const labelW = node.widgets?.find(w => w.name === "label");
            const projW = node.widgets?.find(w => w.name === "project_name");
            const label = labelW?.value || "";
            const project = projW?.value || "?";
            node.title = label ? `Source: ${label} [${project}]` : `Project Source [${project}]`;
            app.graph?.setDirtyCanvas(true, true);
        }

        // Fetch file list from API and update file_name combo
        async function refreshFiles(node) {
            const urlW = node.widgets?.find(w => w.name === "manager_url");
            const projW = node.widgets?.find(w => w.name === "project_name");
            if (!urlW?.value || !projW?.value) return;

            try {
                const resp = await api.fetchApi(
                    `/json_manager/list_project_files?url=${encodeURIComponent(urlW.value)}&project=${encodeURIComponent(projW.value)}`
                );
                if (!resp.ok) return;
                const data = await resp.json();
                const fileList = (data.files || []).map(f => f.name || f);
                console.log(`[ProjectSource] refreshFiles: got ${fileList.length} files:`, fileList);

                const fileW = node.widgets?.find(w => w.name === "file_name");
                if (fileW) {
                    const currentValue = fileW.value;
                    fileW.options.values = fileList.length > 0 ? fileList : [""];
                    // Keep current selection if still valid
                    if (currentValue && fileList.includes(currentValue)) {
                        fileW.value = currentValue;
                    }
                }
            } catch (e) {
                console.error("[ProjectSource] Failed to refresh files:", e);
            }
        }

        // Notify all ProjectKey nodes referencing this source to re-sync
        function notifyRelays(sourceNode) {
            if (!sourceNode.graph?._nodes) return;
            const labelW = sourceNode.widgets?.find(w => w.name === "label");
            if (!labelW?.value) return;
            console.log(`[ProjectSource] notifyRelays: label="${labelW.value}", scanning ${sourceNode.graph._nodes.length} nodes`);
            let matched = 0;
            for (const node of sourceNode.graph._nodes) {
                if (node.type === "ProjectKey" && node._syncFromSource && node._refreshKeys) {
                    const srcW = node.widgets?.find(w => w.name === "source_label");
                    console.log(`[ProjectSource]   ProjectKey id=${node.id} source_label="${srcW?.value}"`);
                    if (srcW?.value === labelW.value) {
                        matched++;
                        node._syncFromSource();
                        node._refreshKeys();
                    }
                }
            }
            console.log(`[ProjectSource] notifyRelays: matched ${matched} relays`);
        }

        const origOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            origOnNodeCreated?.apply(this, arguments);

            const node = this;

            // Hide project_name — it is auto-filled from the Manager's active project
            const projW = this.widgets?.find(w => w.name === "project_name");
            if (projW) {
                if (projW.origType === undefined) projW.origType = projW.type;
                projW.type = "hidden";
                projW.hidden = true;
                projW.computeSize = () => [0, -4];
            }

            // Replace file_name STRING with a combo
            replaceWithCombo(this, "file_name", [], function (value) {
                notifyRelays(node);
            });

            // Hook manager_url to refresh active project + files + notify relays
            const urlW = this.widgets?.find(w => w.name === "manager_url");
            if (urlW) {
                const origCb = urlW.callback;
                urlW.callback = function (...args) {
                    origCb?.apply(this, args);
                    refreshActiveProject(node).then(() => notifyRelays(node));
                };
            }

            // Hook sequence_number to notify relays
            const seqW = this.widgets?.find(w => w.name === "sequence_number");
            if (seqW) {
                const origCb = seqW.callback;
                seqW.callback = function (...args) {
                    origCb?.apply(this, args);
                    notifyRelays(node);
                };
            }

            // Update title when label changes
            const labelWidget = this.widgets?.find(w => w.name === "label");
            if (labelWidget) {
                const origCallback = labelWidget.callback;
                labelWidget.callback = function (...args) {
                    origCallback?.apply(this, args);
                    _updateTitle(node);
                };
            }

            // Auto-fetch active project on creation
            queueMicrotask(() => refreshActiveProject(node));
        };

        const origOnConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function (info) {
            origOnConfigure?.apply(this, arguments);

            // Hide project_name (may have been serialized as visible)
            const projW = this.widgets?.find(w => w.name === "project_name");
            if (projW) {
                if (projW.origType === undefined) projW.origType = projW.type;
                projW.type = "hidden";
                projW.hidden = true;
                projW.computeSize = () => [0, -4];
            }

            // Ensure file_name is a combo (may be STRING from serialization)
            const fileW = this.widgets?.find(w => w.name === "file_name");
            if (fileW && fileW.type !== "combo") {
                const node = this;
                replaceWithCombo(this, "file_name", [], function (value) {
                    notifyRelays(node);
                });
            }

            _updateTitle(this);

            // Deferred: fetch active project (and files) once graph is ready
            const node = this;
            queueMicrotask(() => refreshActiveProject(node));
        };

        // Re-check active project on click (picks up changes made in the Manager)
        const origOnMouseDown = nodeType.prototype.onMouseDown;
        nodeType.prototype.onMouseDown = function (e, localPos, graphCanvas) {
            origOnMouseDown?.apply(this, arguments);
            refreshActiveProject(this);
        };
    },
});
