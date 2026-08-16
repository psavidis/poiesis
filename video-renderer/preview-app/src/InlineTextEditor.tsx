import { useEffect, useRef, useState } from "react";
import { getMoments, getTitleScenes, saveMoments, saveTitleScenes } from "./api";
import { momentIndexFromSceneId } from "./momentDuration";

// Moment treatments with a single plain-text field — matches
// MomentEditorPanel's own condition for rendering its free-text input
// (excludes side-image/side-terms/side-diagram/side-code/comparison, which
// have no single m.text field to edit this way). Kept here rather than
// exported from MomentEditorPanel since this is the *eligibility* check
// (used before opening this editor at all), not the render condition.
const TEXT_ELIGIBLE_TREATMENTS = new Set(["bottom-callout", "side-text", "full-visual"]);

export function isTextEligible(target: EditTarget): boolean {
    if (target.kind === "title") return true;
    return TEXT_ELIGIBLE_TREATMENTS.has(target.treatment);
}

export type EditTarget =
    | { kind: "title"; titleText: string }
    | { kind: "moment"; sceneId: string; treatment: string };

interface Props {
    episodePath: string;
    target: EditTarget;
    // Screen position (from the clicked bar segment / chip) to anchor the
    // floating box near — not inside the Remotion composition itself (see
    // #34's calibration: a floating box near the player, not true in-place
    // editing at the text's exact rendered position/font/treatment, which
    // would need custom layout math per treatment).
    anchor: { x: number; y: number };
    onSaved: () => void;
    onClose: () => void;
}

// A lightweight, text-only sibling to TitleEditorPanel/MomentEditorPanel —
// for the common case of "just fix this wording" without opening the full
// structured editor (asset pickers, term levels, timing). Saves through the
// exact same deterministic endpoints those panels already use
// (saveTitleScenes/saveMoments), so there's still only one write path per
// artifact, just a faster way to reach it for the single-text-field case.
export function InlineTextEditor({ episodePath, target, anchor, onSaved, onClose }: Props) {
    const [text, setText] = useState("");
    const [loaded, setLoaded] = useState(false);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const boxRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        setLoaded(false);
        setError(null);

        if (target.kind === "title") {
            getTitleScenes(episodePath)
                .then((titles) => {
                    const found = titles.find((t) => t.text === target.titleText);
                    setText(found?.text ?? target.titleText);
                    setLoaded(true);
                })
                .catch((e) => setError(String(e)));
        } else {
            const index = momentIndexFromSceneId(target.sceneId);
            getMoments(episodePath)
                .then((data) => {
                    const moments = data.moments ?? [];
                    const moment = index !== null ? moments[index] : undefined;
                    setText(moment?.text ?? "");
                    setLoaded(true);
                })
                .catch((e) => setError(String(e)));
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [episodePath, target]);

    useEffect(() => {
        if (loaded) inputRef.current?.focus();
    }, [loaded]);

    useEffect(() => {
        const onOutsideClick = (e: MouseEvent) => {
            if (boxRef.current && !boxRef.current.contains(e.target as Node)) onClose();
        };
        document.addEventListener("mousedown", onOutsideClick);
        return () => document.removeEventListener("mousedown", onOutsideClick);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const handleSave = async () => {
        setSaving(true);
        setError(null);
        try {
            if (target.kind === "title") {
                const titles = await getTitleScenes(episodePath);
                const index = titles.findIndex((t) => t.text === target.titleText);
                if (index === -1) throw new Error("This title no longer exists — it may have been edited elsewhere.");
                const next = titles.map((t, i) => (i === index ? { ...t, text } : t));
                await saveTitleScenes(episodePath, next);
            } else {
                const index = momentIndexFromSceneId(target.sceneId);
                const data = await getMoments(episodePath);
                const moments = data.moments ?? [];
                if (index === null || !moments[index]) {
                    throw new Error("This moment no longer exists — it may have been edited elsewhere.");
                }
                const next = moments.map((m: any, i: number) => (i === index ? { ...m, text } : m));
                await saveMoments(episodePath, next);
            }
            onSaved();
            onClose();
        } catch (e) {
            setError(String(e));
            setSaving(false);
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === "Enter") {
            e.preventDefault();
            handleSave();
        } else if (e.key === "Escape") {
            e.preventDefault();
            onClose();
        }
    };

    // Clamp so the box stays on screen even when the anchor is near an edge.
    const left = Math.min(Math.max(anchor.x - 140, 8), window.innerWidth - 288);
    const top = Math.max(anchor.y - 56, 8);

    return (
        <div ref={boxRef} style={{ ...styles.wrap, left, top }}>
            {!loaded && !error && <div style={styles.hint}>Loading…</div>}

            {error && <div style={styles.error}>{error}</div>}

            {loaded && (
                <>
                    <input
                        ref={inputRef}
                        type="text"
                        value={text}
                        onChange={(e) => setText(e.target.value)}
                        onKeyDown={handleKeyDown}
                        disabled={saving}
                        style={styles.input}
                    />
                    <div style={styles.actions}>
                        <button onClick={handleSave} disabled={saving} style={styles.saveBtn}>
                            {saving ? "Saving…" : "Save"}
                        </button>
                        <button className="secondary small" onClick={onClose} disabled={saving}>
                            Cancel
                        </button>
                    </div>
                </>
            )}
        </div>
    );
}

const styles: Record<string, React.CSSProperties> = {
    wrap: {
        position: "fixed",
        zIndex: 50,
        display: "flex",
        flexDirection: "column",
        gap: 6,
        width: 280,
        padding: 10,
        background: "#161d24",
        border: "1px solid #3a4552",
        borderRadius: 8,
        boxShadow: "0 8px 24px rgba(0,0,0,0.5)",
    },
    input: {
        width: "100%",
        boxSizing: "border-box",
        padding: "6px 10px",
        background: "#0b0f14",
        border: "1px solid #2a333d",
        borderRadius: 6,
        color: "#e8edf2",
        fontSize: 13,
    },
    actions: {
        display: "flex",
        gap: 8,
    },
    saveBtn: {
        fontSize: 12,
        padding: "4px 10px",
    },
    hint: {
        fontSize: 12,
        color: "#9aa7b4",
    },
    error: {
        fontSize: 12,
        color: "#ff8f8f",
    },
};
