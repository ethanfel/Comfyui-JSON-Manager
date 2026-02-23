import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

app.registerExtension({
    name: "json.manager.dynamic",

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name !== "JSONLoaderDynamic") return;

        const origOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            origOnNodeCreated?.apply(this, arguments);

            // Hide the output_keys widget (managed internally by JS)
            const okWidget = this.widgets?.find(w => w.name === "output_keys");
            if (okWidget) {
                okWidget.type = "hidden";
                okWidget.computeSize = () => [0, -4];
            }

            // Hide all 32 outputs initially
            this._dynamicOutputCount = 0;
            for (let i = 0; i < this.outputs.length; i++) {
                this.outputs[i]._visible = false;
            }

            // Add Refresh button
            this.addWidget("button", "Refresh Outputs", null, () => {
                this.refreshDynamicOutputs();
            });

            // Store original outputs array for show/hide
            this._allOutputs = [...this.outputs];
            // Start with no visible outputs
            this.outputs.length = 0;
        };

        nodeType.prototype.refreshDynamicOutputs = async function () {
            const pathWidget = this.widgets?.find(w => w.name === "json_path");
            const seqWidget = this.widgets?.find(w => w.name === "sequence_number");
            if (!pathWidget?.value) return;

            try {
                const resp = await api.fetchApi(
                    `/json_manager/get_keys?path=${encodeURIComponent(pathWidget.value)}&sequence_number=${seqWidget?.value || 1}`
                );
                const { keys } = await resp.json();

                // Update output_keys widget for Python to read
                const okWidget = this.widgets?.find(w => w.name === "output_keys");
                if (okWidget) okWidget.value = keys.join(",");

                // Restore full outputs array to manipulate
                if (this._allOutputs) {
                    this.outputs = this._allOutputs;
                }

                // Disconnect any links on outputs that will be hidden
                for (let i = keys.length; i < 32; i++) {
                    if (this.outputs[i]?.links?.length) {
                        for (const linkId of [...this.outputs[i].links]) {
                            this.graph?.removeLink(linkId);
                        }
                    }
                }

                // Rename visible outputs to key names
                for (let i = 0; i < 32; i++) {
                    if (i < keys.length) {
                        this.outputs[i].name = keys[i];
                        this.outputs[i]._visible = true;
                    } else {
                        this.outputs[i].name = `output_${i}`;
                        this.outputs[i]._visible = false;
                    }
                }

                // Truncate outputs array to only show active ones
                this._dynamicOutputCount = keys.length;
                this._allOutputs = [...this.outputs];
                this.outputs.length = keys.length;

                this.setSize(this.computeSize());
                app.graph.setDirtyCanvas(true, true);
            } catch (e) {
                console.error("[JSONLoaderDynamic] Refresh failed:", e);
            }
        };

        // Override configure to restore state on workflow load
        const origOnConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function (info) {
            origOnConfigure?.apply(this, arguments);

            const okWidget = this.widgets?.find(w => w.name === "output_keys");
            if (okWidget) {
                okWidget.type = "hidden";
                okWidget.computeSize = () => [0, -4];
            }

            const keys = okWidget?.value
                ? okWidget.value.split(",").filter(k => k.trim())
                : [];

            // Ensure we have the full 32 outputs stored
            this._allOutputs = [...this.outputs];
            while (this._allOutputs.length < 32) {
                this._allOutputs.push({
                    name: `output_${this._allOutputs.length}`,
                    type: "*",
                    links: null,
                    _visible: false,
                });
            }

            // Rename and set visibility
            for (let i = 0; i < 32; i++) {
                if (i < keys.length) {
                    this._allOutputs[i].name = keys[i].trim();
                    this._allOutputs[i]._visible = true;
                } else {
                    this._allOutputs[i].name = `output_${i}`;
                    this._allOutputs[i]._visible = false;
                }
            }

            this._dynamicOutputCount = keys.length;
            this.outputs = this._allOutputs.slice(0, keys.length);

            this.setSize(this.computeSize());
        };
    },
});
