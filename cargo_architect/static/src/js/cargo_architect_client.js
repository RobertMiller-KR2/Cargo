/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onMounted, useRef, useState } from "@odoo/owl";

export class CargoArchitectPlanner extends Component {
    static template = "cargo_architect.Planner";
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.topCanvasRef = useRef("topCanvas");
        this.leftCanvasRef = useRef("leftCanvas");
        this.rightCanvasRef = useRef("rightCanvas");
        this.planId = this.props.action?.params?.plan_id || this.props.action?.context?.active_id;
        this.state = useState({
            plan: {},
            placements: [],
            planName: "",
            loading: false,
            activeView: "top",
            warning: "",
            selectedPlacementId: null,
            selectedPlacementIds: [],
            snapGridIn: 2,
            manualMessage: "All views are visible. Drag in Top View to move length/width. Drag in Left or Right Side View to stack/unstack by length/height. Dropped blocks are locked automatically."
        });
        this.drag = null;
        this.canvasTransforms = {};
        onMounted(async () => {
            await this.reload();
            window.addEventListener("resize", () => this.drawCanvas());
        });
    }
    formatNumber(value) {
        return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 1 });
    }
    setActiveView(mode) {
        this.state.activeView = mode;
        this.drag = null;
        this.drawCanvas();
    }
    getViewLabel(mode) {
        if (mode === "left") return "Left Side View - drag blocks to stack/unstack";
        if (mode === "right") return "Right Side View - drag blocks to stack/unstack";
        return "Top View - drag blocks to move length/width";
    }
    get selectedPlacement() {
        return this.state.placements.find((p) => p.id === this.state.selectedPlacementId) || null;
    }
    get selectedPlacements() {
        const ids = new Set(this.state.selectedPlacementIds || []);
        return this.state.placements.filter((p) => ids.has(p.id));
    }
    isSelected(id) {
        return (this.state.selectedPlacementIds || []).includes(id);
    }
    selectPlacement(id, additive = false) {
        if (additive) {
            const ids = new Set(this.state.selectedPlacementIds || []);
            if (ids.has(id)) ids.delete(id);
            else ids.add(id);
            this.state.selectedPlacementIds = [...ids];
            this.state.selectedPlacementId = id;
        } else {
            this.state.selectedPlacementId = id;
            this.state.selectedPlacementIds = id ? [id] : [];
        }
        this.drawCanvas();
    }
    clearSelection() {
        this.state.selectedPlacementId = null;
        this.state.selectedPlacementIds = [];
        this.drawCanvas();
    }
    selectAllPlacements() {
        this.state.selectedPlacementIds = this.state.placements.map((p) => p.id);
        this.state.selectedPlacementId = this.state.selectedPlacementIds[0] || null;
        this.state.manualMessage = `${this.state.selectedPlacementIds.length} placement(s) selected.`;
        this.drawCanvas();
    }
    async reload() {
        if (!this.planId) return;
        this.state.loading = true;
        const plans = await this.orm.read("cargo.architect.load.plan", [this.planId], [
            "name", "length_in", "width_in", "height_in", "requested_qty", "loaded_qty", "total_weight_lbs",
            "cube_utilization", "floor_utilization", "load_quality_score", "steer_axle_lbs", "drive_axle_lbs", "trailer_axle_lbs", "unplaced_json",
        ]);
        this.state.plan = plans[0] || {};
        this.state.planName = this.state.plan.name;
        this.state.warning = this.getUnplacedWarning(this.state.plan.unplaced_json);
        this.state.placements = await this.orm.searchRead("cargo.architect.placement", [["plan_id", "=", this.planId]], [
            "name", "x_in", "y_in", "z_in", "length_in", "width_in", "height_in", "weight_lbs", "locked"
        ], { order: "sequence asc, id asc" });
        const validIds = new Set(this.state.placements.map((p) => p.id));
        this.state.selectedPlacementIds = (this.state.selectedPlacementIds || []).filter((id) => validIds.has(id));
        if (this.state.selectedPlacementId && !validIds.has(this.state.selectedPlacementId)) {
            this.state.selectedPlacementId = this.state.selectedPlacementIds[0] || null;
        }
        this.state.loading = false;
        this.drawCanvas();
    }
    async backToLoadPlan() {
        if (!this.planId) {
            this.action.restore();
            return;
        }
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: "Load Plan",
            res_model: "cargo.architect.load.plan",
            res_id: this.planId,
            views: [[false, "form"]],
            view_mode: "form",
            target: "current",
        });
    }
    async optimize() {
        if (!this.planId) return;
        this.state.loading = true;
        const result = await this.orm.call("cargo.architect.load.plan", "action_optimize_layout", [[this.planId]]);
        await this.reload();
        if (result && result.type) await this.action.doAction(result);
    }
    async reoptimizeAroundLocked() {
        if (!this.planId) return;
        this.state.loading = true;
        const result = await this.orm.call("cargo.architect.load.plan", "action_reoptimize_around_locked", [[this.planId]]);
        await this.reload();
        if (result && result.type) await this.action.doAction(result);
    }
    async toggleLockSelected() {
        const selected = this.selectedPlacement;
        if (!selected) return;
        await this.orm.write("cargo.architect.placement", [selected.id], { locked: !selected.locked });
        selected.locked = !selected.locked;
        this.drawCanvas();
    }
    async unlockSelected() {
        const selected = this.selectedPlacement;
        if (!selected) return;
        await this.unlockPlacement(selected.id);
    }
    async unlockPlacement(id) {
        if (!id) return;
        await this.orm.call("cargo.architect.placement", "action_unlock_placement", [[id]]);
        this.state.manualMessage = "Placement unlocked. The optimizer may move it on the next run.";
        await this.reload();
    }
    async unlockAllPlacements() {
        if (!this.planId) return;
        const result = await this.orm.call("cargo.architect.load.plan", "action_unlock_all_placements", [[this.planId]]);
        this.state.manualMessage = "All placements unlocked. The optimizer may move them on the next run.";
        await this.reload();
        if (result && result.type) await this.action.doAction(result);
    }
    getUnplacedWarning(value) {
        if (!value) return "";
        try {
            const data = JSON.parse(value || "{}");
            const parts = Object.entries(data).filter(([, qty]) => Number(qty || 0) > 0).map(([name, qty]) => `${name}: ${qty}`);
            return parts.length ? `Not all items fit: ${parts.join(", ")}` : "";
        } catch (error) {
            return "";
        }
    }
    getSelectedOrActivePlacements() {
        const selected = this.selectedPlacements;
        return selected.length ? selected : (this.selectedPlacement ? [this.selectedPlacement] : []);
    }
    applySnap(value) {
        const grid = Number(this.state.snapGridIn || 0);
        if (!grid || grid <= 0) return Math.round(Number(value || 0) * 10) / 10;
        return Math.round(Number(value || 0) / grid) * grid;
    }
    async savePlacementPositions(placements, message) {
        if (!this.planId || !placements.length) return;
        for (const p of placements) {
            const result = await this.orm.call("cargo.architect.load.plan", "action_update_placement_position", [[this.planId], p.id, p.x_in, p.y_in, p.z_in || 0, true]);
            if (result && result.ok === false) {
                this.notification.add(result.message || "Cannot move selected block(s) here.", { type: "warning" });
                await this.reload();
                return;
            }
        }
        this.state.manualMessage = message || `${placements.length} placement(s) moved and locked.`;
        await this.reload();
    }
    async snapSelectedToGrid() {
        const placements = this.getSelectedOrActivePlacements();
        placements.forEach((p) => {
            p.x_in = this.applySnap(p.x_in);
            p.y_in = this.applySnap(p.y_in);
            p.z_in = this.applySnap(p.z_in || 0);
        });
        await this.savePlacementPositions(placements, `Snapped ${placements.length} placement(s) to ${this.state.snapGridIn} in grid.`);
    }
    async alignSelected(axis, mode) {
        const placements = this.getSelectedOrActivePlacements();
        if (placements.length < 2) {
            this.notification.add("Select two or more placements for alignment.", { type: "warning" });
            return;
        }
        if (axis === "x") {
            const minX = Math.min(...placements.map((p) => Number(p.x_in || 0)));
            const maxX = Math.max(...placements.map((p) => Number(p.x_in || 0) + Number(p.length_in || 0)));
            const center = (minX + maxX) / 2.0;
            placements.forEach((p) => {
                if (mode === "min") p.x_in = minX;
                else if (mode === "max") p.x_in = maxX - Number(p.length_in || 0);
                else p.x_in = center - Number(p.length_in || 0) / 2.0;
                p.x_in = this.applySnap(p.x_in);
            });
        } else if (axis === "y") {
            const minY = Math.min(...placements.map((p) => Number(p.y_in || 0)));
            const maxY = Math.max(...placements.map((p) => Number(p.y_in || 0) + Number(p.width_in || 0)));
            const center = (minY + maxY) / 2.0;
            placements.forEach((p) => {
                if (mode === "min") p.y_in = minY;
                else if (mode === "max") p.y_in = maxY - Number(p.width_in || 0);
                else p.y_in = center - Number(p.width_in || 0) / 2.0;
                p.y_in = this.applySnap(p.y_in);
            });
        }
        await this.savePlacementPositions(placements, `Aligned ${placements.length} placement(s).`);
    }
    async distributeSelected(axis) {
        const placements = [...this.getSelectedOrActivePlacements()];
        if (placements.length < 3) {
            this.notification.add("Select three or more placements to distribute evenly.", { type: "warning" });
            return;
        }
        const key = axis === "x" ? "x_in" : "y_in";
        const sizeKey = axis === "x" ? "length_in" : "width_in";
        placements.sort((a, b) => Number(a[key] || 0) - Number(b[key] || 0));
        const first = placements[0];
        const last = placements[placements.length - 1];
        const start = Number(first[key] || 0);
        const end = Number(last[key] || 0) + Number(last[sizeKey] || 0);
        const totalSize = placements.reduce((sum, p) => sum + Number(p[sizeKey] || 0), 0);
        const gap = Math.max(0, (end - start - totalSize) / (placements.length - 1));
        let pos = start;
        placements.forEach((p) => {
            p[key] = this.applySnap(pos);
            pos += Number(p[sizeKey] || 0) + gap;
        });
        await this.savePlacementPositions(placements, `Distributed ${placements.length} placement(s) evenly.`);
    }
    getCanvasRef(mode) {
        if (mode === "left") return this.leftCanvasRef;
        if (mode === "right") return this.rightCanvasRef;
        return this.topCanvasRef;
    }
    getCanvasPoint(ev, mode) {
        const canvas = this.getCanvasRef(mode).el;
        const rect = canvas.getBoundingClientRect();
        const scaleX = canvas.width / rect.width;
        const scaleY = canvas.height / rect.height;
        return { x: (ev.clientX - rect.left) * scaleX, y: (ev.clientY - rect.top) * scaleY };
    }
    getPlacementAtCanvasPoint(point, mode) {
        const t = this.canvasTransforms[mode];
        if (!t) return null;
        const placements = [...this.state.placements].reverse();
        for (const p of placements) {
            if (mode === "left" || mode === "right") {
                const px = Number(p.x_in || 0);
                const pz = Number(p.z_in || 0);
                const pl = Number(p.length_in || 0);
                const ph = Number(p.height_in || 0);
                const xRaw = mode === "right" ? (t.planLength - px - pl) : px;
                const x = t.ox + xRaw * t.scale;
                const y = t.oy + t.trailerH - (pz + ph) * t.scale;
                const w = Math.max(pl * t.scale, 2);
                const h = Math.max(ph * t.scale, 2);
                if (point.x >= x && point.x <= x + w && point.y >= y && point.y <= y + h) return p;
            } else {
                const x = t.ox + Number(p.x_in || 0) * t.scale;
                const y = t.oy + Number(p.y_in || 0) * t.scale;
                const w = Math.max(Number(p.length_in || 0) * t.scale, 2);
                const h = Math.max(Number(p.width_in || 0) * t.scale, 2);
                if (point.x >= x && point.x <= x + w && point.y >= y && point.y <= y + h) return p;
            }
        }
        return null;
    }
    onCanvasMouseDown(ev, mode) {
        const point = this.getCanvasPoint(ev, mode);
        const placement = this.getPlacementAtCanvasPoint(point, mode);
        const t = this.canvasTransforms[mode];
        if (!placement || !t) return;
        this.state.activeView = mode;
        const additive = !!(ev.ctrlKey || ev.metaKey || ev.shiftKey);
        this.selectPlacement(placement.id, additive);
        const px = Number(placement.x_in || 0);
        const py = Number(placement.y_in || 0);
        const pz = Number(placement.z_in || 0);
        const pl = Number(placement.length_in || 0);
        const ph = Number(placement.height_in || 0);
        const xRaw = mode === "right" ? (t.planLength - px - pl) : px;
        this.drag = {
            id: placement.id,
            mode: mode,
            startX: px,
            startY: py,
            startZ: pz,
            offsetX: (point.x - (t.ox + xRaw * t.scale)) / t.scale,
            offsetY: (point.y - (t.oy + py * t.scale)) / t.scale,
            offsetZ: (point.y - (t.oy + (t.trailerH || 0) - (pz + ph) * t.scale)) / t.scale,
            groupStarts: this.getSelectedOrActivePlacements().map((p) => ({ id: p.id, x: Number(p.x_in || 0), y: Number(p.y_in || 0), z: Number(p.z_in || 0) })),
        };
        ev.preventDefault();
        this.drawCanvas();
    }
    onCanvasMouseMove(ev, mode) {
        if (!this.drag) return;
        const t = this.canvasTransforms[this.drag.mode];
        if (!t || mode !== this.drag.mode) return;
        const point = this.getCanvasPoint(ev, this.drag.mode);
        const placement = this.state.placements.find((p) => p.id === this.drag.id);
        if (!placement) return;
        const planLength = Number(this.state.plan.length_in || 636);
        const planWidth = Number(this.state.plan.width_in || 98);
        const planHeight = Number(this.state.plan.height_in || 110);
        const pLength = Number(placement.length_in || 0);
        const pWidth = Number(placement.width_in || 0);
        const pHeight = Number(placement.height_in || 0);
        if (this.drag.mode === "left" || this.drag.mode === "right") {
            let newRawX = (point.x - t.ox) / t.scale - this.drag.offsetX;
            let newX = this.drag.mode === "right" ? (planLength - newRawX - pLength) : newRawX;
            let newTopY = point.y - this.drag.offsetZ * t.scale;
            let newZ = (t.oy + t.trailerH - newTopY) / t.scale - pHeight;
            newX = Math.max(0, Math.min(planLength - pLength, newX));
            newZ = Math.max(0, Math.min(planHeight - pHeight, newZ));
            placement.x_in = this.applySnap(newX);
            placement.z_in = this.applySnap(newZ);
            const dx = placement.x_in - this.drag.startX;
            const dz = placement.z_in - this.drag.startZ;
            (this.drag.groupStarts || []).forEach((start) => {
                if (start.id === placement.id) return;
                const gp = this.state.placements.find((item) => item.id === start.id);
                if (!gp) return;
                gp.x_in = this.applySnap(Math.max(0, Math.min(planLength - Number(gp.length_in || 0), start.x + dx)));
                gp.z_in = this.applySnap(Math.max(0, Math.min(planHeight - Number(gp.height_in || 0), start.z + dz)));
            });
        } else {
            let newX = (point.x - t.ox) / t.scale - this.drag.offsetX;
            let newY = (point.y - t.oy) / t.scale - this.drag.offsetY;
            newX = Math.max(0, Math.min(planLength - pLength, newX));
            newY = Math.max(0, Math.min(planWidth - pWidth, newY));
            placement.x_in = this.applySnap(newX);
            placement.y_in = this.applySnap(newY);
            const dx = placement.x_in - this.drag.startX;
            const dy = placement.y_in - this.drag.startY;
            (this.drag.groupStarts || []).forEach((start) => {
                if (start.id === placement.id) return;
                const gp = this.state.placements.find((item) => item.id === start.id);
                if (!gp) return;
                gp.x_in = this.applySnap(Math.max(0, Math.min(planLength - Number(gp.length_in || 0), start.x + dx)));
                gp.y_in = this.applySnap(Math.max(0, Math.min(planWidth - Number(gp.width_in || 0), start.y + dy)));
            });
        }
        this.drawCanvas();
        ev.preventDefault();
    }
    async onCanvasMouseUp(ev, mode) {
        if (!this.drag) return;
        const placement = this.state.placements.find((p) => p.id === this.drag.id);
        const movedIds = new Set((this.drag.groupStarts || [{ id: this.drag.id }]).map((s) => s.id));
        this.drag = null;
        if (!placement) return;
        try {
            const moved = this.state.placements.filter((p) => movedIds.has(p.id));
            for (const p of moved) {
                const result = await this.orm.call("cargo.architect.load.plan", "action_update_placement_position", [[this.planId], p.id, p.x_in, p.y_in, p.z_in || 0, true]);
                if (result && result.ok === false) {
                    this.notification.add(result.message || "Cannot move selected block(s) here.", { type: "warning" });
                    this.state.manualMessage = result.message || "Manual group move rejected.";
                    await this.reload();
                    ev.preventDefault();
                    return;
                }
            }
            this.state.manualMessage = `${moved.length} placement(s) moved and locked from ${this.getViewLabel(mode)}.`;
            await this.reload();
        } catch (error) {
            const message = error.data?.message || error.message || "Manual move was rejected.";
            this.notification.add(message, { type: "warning" });
            this.state.manualMessage = message;
            await this.reload();
        }
        ev.preventDefault();
    }
    onCanvasMouseLeave(ev, mode) {
        if (this.drag && this.drag.mode === mode) this.onCanvasMouseUp(ev, mode);
    }
    drawCanvas() {
        this.drawView("top");
        this.drawView("left");
        this.drawView("right");
    }
    drawView(mode) {
        const canvas = this.getCanvasRef(mode).el;
        if (!canvas) return;
        const parent = canvas.parentElement;
        const width = Math.max(parent.clientWidth - 4, mode === "top" ? 760 : 420);
        const height = Math.max(parent.clientHeight - 4, mode === "top" ? 330 : 300);
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext("2d");
        ctx.clearRect(0, 0, width, height);
        ctx.fillStyle = "#f8fbff";
        ctx.fillRect(0, 0, width, height);
        const plan = this.state.plan || {};
        const planLength = Number(plan.length_in || 636);
        const planWidth = Number(plan.width_in || 98);
        const planHeight = Number(plan.height_in || 110);
        const margin = 32;
        const colors = ["#60a5fa", "#34d399", "#fbbf24", "#f87171", "#a78bfa", "#22d3ee", "#fb7185"];
        ctx.save();
        ctx.font = "13px sans-serif";
        ctx.fillStyle = mode === this.state.activeView ? "#1d4ed8" : "#0f172a";
        ctx.fillText(this.getViewLabel(mode), margin, 22);
        ctx.restore();
        if (mode === "left" || mode === "right") {
            const scale = Math.min((width - margin * 2) / planLength, (height - margin * 2 - 20) / planHeight);
            const trailerW = planLength * scale;
            const trailerH = planHeight * scale;
            const ox = margin;
            const oy = height - margin - trailerH;
            this.canvasTransforms[mode] = { scale, ox, oy, mode, planLength, planWidth, planHeight, trailerW, trailerH };
            ctx.strokeStyle = mode === this.state.activeView ? "#1d4ed8" : "#64748b";
            ctx.lineWidth = mode === this.state.activeView ? 3 : 2;
            ctx.strokeRect(ox, oy, trailerW, trailerH);
            ctx.fillStyle = "#64748b";
            ctx.font = "12px sans-serif";
            ctx.fillText(`${planLength.toFixed(0)} in L x ${planHeight.toFixed(0)} in H`, ox, oy + trailerH + 18);
            const placements = [...this.state.placements].sort((a, b) => (Number(a.z_in || 0) - Number(b.z_in || 0)) || (Number(a.x_in || 0) - Number(b.x_in || 0)));
            placements.forEach((p, i) => {
                const px = Number(p.x_in || 0);
                const pz = Number(p.z_in || 0);
                const pl = Number(p.length_in || 0);
                const ph = Number(p.height_in || 0);
                const xRaw = mode === "right" ? (planLength - px - pl) : px;
                const x = ox + xRaw * scale;
                const y = oy + trailerH - (pz + ph) * scale;
                const w = Math.max(pl * scale, 2);
                const h = Math.max(ph * scale, 2);
                ctx.fillStyle = colors[i % colors.length];
                ctx.globalAlpha = p.locked ? 0.92 : 0.78;
                ctx.fillRect(x, y, w, h);
                ctx.globalAlpha = 1;
                ctx.strokeStyle = this.isSelected(p.id) ? "#ef4444" : (p.locked ? "#7c3aed" : "#0f172a");
                ctx.lineWidth = this.isSelected(p.id) ? 3 : (p.locked ? 2 : 1);
                ctx.strokeRect(x, y, w, h);
                if (w > 38 && h > 14) {
                    ctx.fillStyle = "#0f172a";
                    ctx.font = "11px sans-serif";
                    ctx.fillText(p.locked ? `${p.name} 🔒` : p.name, x + 4, y + 13);
                }
            });
        } else {
            const scale = Math.min((width - margin * 2) / planLength, (height - margin * 2 - 20) / planWidth);
            const ox = margin;
            const oy = margin;
            this.canvasTransforms[mode] = { scale, ox, oy, mode: "top", planLength, planWidth, planHeight };
            ctx.strokeStyle = mode === this.state.activeView ? "#1d4ed8" : "#64748b";
            ctx.lineWidth = mode === this.state.activeView ? 3 : 2;
            ctx.strokeRect(ox, oy, planLength * scale, planWidth * scale);
            ctx.strokeStyle = "#94a3b8";
            ctx.lineWidth = 1;
            ctx.setLineDash([6, 4]);
            ctx.beginPath();
            ctx.moveTo(ox, oy + (planWidth / 2) * scale);
            ctx.lineTo(ox + planLength * scale, oy + (planWidth / 2) * scale);
            ctx.stroke();
            ctx.setLineDash([]);
            this.state.placements.forEach((p, i) => {
                const x = ox + Number(p.x_in || 0) * scale;
                const y = oy + Number(p.y_in || 0) * scale;
                const w = Math.max(Number(p.length_in || 0) * scale, 2);
                const h = Math.max(Number(p.width_in || 0) * scale, 2);
                ctx.fillStyle = colors[i % colors.length];
                ctx.globalAlpha = p.locked ? 0.92 : 0.78;
                ctx.fillRect(x, y, w, h);
                ctx.globalAlpha = 1;
                ctx.strokeStyle = this.isSelected(p.id) ? "#ef4444" : (p.locked ? "#7c3aed" : "#0f172a");
                ctx.lineWidth = this.isSelected(p.id) ? 3 : (p.locked ? 2 : 1);
                ctx.strokeRect(x, y, w, h);
                if (w > 38 && h > 14) {
                    ctx.fillStyle = "#0f172a";
                    ctx.font = "11px sans-serif";
                    ctx.fillText(p.locked ? `${p.name} 🔒` : p.name, x + 4, y + 13);
                }
            });
        }
    }
}

registry.category("actions").add("cargo_architect_planner", CargoArchitectPlanner);
