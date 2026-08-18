import { useEffect, useRef, useState } from "react";
import { getBeats, getMoments, getTitleScenes, saveBeats, saveMoments, saveTitleScenes } from "./api";
import { momentIndexFromSceneId } from "./momentDuration";
import { colors, radius, shadow, typography } from "./tokens";

// Moment treatments with a single plain-text field — matches
// MomentEditorPanel's own condition for rendering its free-text input
// (excludes side-image/side-terms/side-diagram/side-code/comparison, which
// have no single m.text field to edit this way). Kept here rather than
// exported from MomentEditorPanel since this is the *eligibility* check
// (used before opening this editor at all), not the render condition.
const TEXT_ELIGIBLE_TREATMENTS = new Set(["bottom-callout", "side-text", "full-visual"]);

export function isTextEligible(target: EditTarget): boolean {
    if (target.kind === "title" || target.kind === "new-title" || target.kind === "beat") return true;
    return TEXT_ELIGIBLE_TREATMENTS.has(target.treatment);
}

// scene-beat-{N} is exactly the array index of emphasis.json's beats list
// (see generate_emphasis.py's merge_beat_scenes) — same exact-index
// convention momentIndexFromSceneId already relies on for moments.
function beatIndexFromSceneId(sceneId: string): number | null {
    const match = /^scene-beat-(\d+)$/.exec(sceneId);
    return match ? Number(match[1]) : null;
}

export type EditTarget =
    | { kind: "title"; titleText: string }
    // The lead-in chapter (before the first title card) has no underlying
    // title_scenes.json entry by design (#83) — editing it for the first
    // time creates one at newTitleSegmentId rather than matching an
    // existing entry by text, unlike every other title edit.
    | { kind: "new-title"; newTitleSegmentId: string }
    | { kind: "moment"; sceneId: string; treatment: string }
    | { kind: "beat"; sceneId: string };

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
    // Fires on every keystroke (before the real save) so the caller can
    // patch its own local player state and show the edit in the preview
    // immediately, not just after the real save commits (see #39). Optional
    // — title/moment editing has no live-preview requirement, only beats do.
    onLiveChange?: (text: string) => void;
}

// A lightweight, text-only sibling to TitleEditorPanel/MomentEditorPanel —
// for the common case of "just fix this wording" without opening the full
// structured editor (asset pickers, term levels, timing). Saves through the
// exact same deterministic endpoints those panels already use
// (saveTitleScenes/saveMoments), so there's still only one write path per
// artifact, just a faster way to reach it for the single-text-field case.
export function InlineTextEditor({ episodePath, target, anchor, onSaved, onClose, onLiveChange }: Props) {
    const [text, setText] = useState("");
    const [loaded, setLoaded] = useState(false);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);
    // Only meaningful for kind "beat" (#58) or "title" (#59) — neither has
    // a structured property panel with its own reset UI always in view
    // (titles have TitleEditorPanel, but this box is a separate, faster
    // entry point to the same data), so this box is also where "text was
    // manually edited" state and its reset affordance live for both.
    // Moments are excluded — MomentEditorPanel already owns that for them.
    // undefined until loaded; empty array once loaded but not overridden.
    const [textOverriddenFields, setTextOverriddenFields] = useState<string[] | undefined>(undefined);
    const boxRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLInputElement>(null);
    // The text as originally loaded, so cancelling (Escape / outside-click)
    // can revert onLiveChange's mid-typing preview patch back to what it
    // was before this editor opened, not leave the player showing
    // whatever was last typed but never actually saved.
    const originalTextRef = useRef("");

    useEffect(() => {
        setLoaded(false);
        setError(null);

        if (target.kind === "title") {
            getTitleScenes(episodePath)
                .then((titles) => {
                    const found = titles.find((t) => t.text === target.titleText);
                    const initial = found?.text ?? target.titleText;
                    setText(initial);
                    originalTextRef.current = initial;
                    setTextOverriddenFields(found?.overriddenFields ?? []);
                    setLoaded(true);
                })
                .catch((e) => setError(String(e)));
        } else if (target.kind === "new-title") {
            // Nothing to fetch — this chapter has no existing entry yet, so
            // the box just opens empty, same first-run feel as any other
            // "add text" field.
            setText("");
            originalTextRef.current = "";
            setTextOverriddenFields([]);
            setLoaded(true);
        } else if (target.kind === "beat") {
            const index = beatIndexFromSceneId(target.sceneId);
            getBeats(episodePath)
                .then((data) => {
                    const beats = data.beats ?? [];
                    const beat = index !== null ? beats[index] : undefined;
                    const initial = beat?.text ?? "";
                    setText(initial);
                    originalTextRef.current = initial;
                    setTextOverriddenFields(beat?.overriddenFields ?? []);
                    setLoaded(true);
                })
                .catch((e) => setError(String(e)));
        } else {
            const index = momentIndexFromSceneId(target.sceneId);
            getMoments(episodePath)
                .then((data) => {
                    const moments = data.moments ?? [];
                    const moment = index !== null ? moments[index] : undefined;
                    const initial = moment?.text ?? "";
                    setText(initial);
                    originalTextRef.current = initial;
                    setLoaded(true);
                })
                .catch((e) => setError(String(e)));
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [episodePath, target]);

    useEffect(() => {
        if (loaded) inputRef.current?.focus();
    }, [loaded]);

    // Reverts onLiveChange's mid-typing preview patch back to the
    // originally-loaded text before closing — without this, cancelling
    // (Escape or clicking away) would leave the player showing whatever
    // was last typed even though nothing was actually saved.
    const handleCancel = () => {
        onLiveChange?.(originalTextRef.current);
        onClose();
    };

    useEffect(() => {
        const onOutsideClick = (e: MouseEvent) => {
            if (boxRef.current && !boxRef.current.contains(e.target as Node)) handleCancel();
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
                // overriddenFields is sent explicitly (not just left to
                // round-trip) so a pending Reset-to-Automatic click (#59)
                // takes effect on save — the server still recomputes it
                // from a segmentId-matched diff on top, same as beats (#58).
                const next = titles.map((t, i) =>
                    i === index ? { ...t, text, overriddenFields: textOverriddenFields ?? t.overriddenFields } : t
                );
                await saveTitleScenes(episodePath, next);
            } else if (target.kind === "new-title") {
                if (!text.trim()) throw new Error("Enter a title before saving.");
                const titles = await getTitleScenes(episodePath);
                await saveTitleScenes(episodePath, [
                    ...titles,
                    { segmentId: target.newTitleSegmentId, text, overriddenFields: ["text"] },
                ]);
            } else if (target.kind === "beat") {
                const index = beatIndexFromSceneId(target.sceneId);
                const data = await getBeats(episodePath);
                const beats = data.beats ?? [];
                if (index === null || !beats[index]) {
                    throw new Error("This beat no longer exists — it may have been edited elsewhere.");
                }
                // overriddenFields is sent explicitly (not just left to
                // round-trip) so a pending Reset-to-Automatic click (#58)
                // takes effect on save — the server still recomputes it
                // from a value diff on top, same as moments (#57).
                const next = beats.map((b: any, i: number) =>
                    i === index ? { ...b, text, overriddenFields: textOverriddenFields ?? b.overriddenFields } : b
                );
                await saveBeats(episodePath, next);
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
            handleCancel();
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
                        onChange={(e) => {
                            setText(e.target.value);
                            onLiveChange?.(e.target.value);
                        }}
                        onKeyDown={handleKeyDown}
                        disabled={saving}
                        style={styles.input}
                    />
                    <div style={styles.actions}>
                        <button onClick={handleSave} disabled={saving} style={styles.saveBtn}>
                            {saving ? "Saving…" : "Save"}
                        </button>
                        <button className="secondary small" onClick={handleCancel} disabled={saving}>
                            Cancel
                        </button>
                        {(target.kind === "beat" || target.kind === "title") && textOverriddenFields?.includes("text") && (
                            <button
                                type="button"
                                className="secondary small"
                                disabled={saving}
                                onClick={() => setTextOverriddenFields((prev) => (prev || []).filter((f) => f !== "text"))}
                                title="This text was manually edited — reset to let the AI decide it again next time"
                            >
                                Reset to Automatic
                            </button>
                        )}
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
        background: colors.surface,
        border: `1px solid ${colors.borderStrong}`,
        borderRadius: radius.lg,
        boxShadow: shadow.elevated,
    },
    input: {
        width: "100%",
        boxSizing: "border-box",
        padding: "6px 10px",
        background: colors.background,
        border: `1px solid ${colors.border}`,
        borderRadius: radius.md,
        color: colors.textPrimary,
        fontSize: typography.size.md,
    },
    actions: {
        display: "flex",
        gap: 8,
    },
    saveBtn: {
        fontSize: typography.size.sm,
        padding: "4px 10px",
    },
    hint: {
        fontSize: typography.size.sm,
        color: colors.textSecondary,
    },
    error: {
        fontSize: typography.size.sm,
        color: colors.error,
    },
};
