"use client";

import { useActionState, useState } from "react";

import { createCapture } from "./actions";
import { initialCaptureState } from "./capture-state";

export function CaptureForm() {
  const [state, formAction, isPending] = useActionState(
    createCapture,
    initialCaptureState,
  );

  // React's post-action form reset restores each select to the option that was
  // selected when it mounted, and ignores later defaultValue changes. Remount
  // the select for every action result so its default (the submitted type on
  // error, Text on success) is what the reset restores.
  const [seenState, setSeenState] = useState(state);
  const [selectKey, setSelectKey] = useState(0);
  const [dismissedState, setDismissedState] = useState(state);
  if (seenState !== state) {
    setSeenState(state);
    setSelectKey((key) => key + 1);
  }

  const showSuccess = state.status === "success" && dismissedState !== state;
  const titleError = state.fieldErrors?.title;
  const contentError = state.fieldErrors?.content;

  return (
    <form
      action={formAction}
      className="capture-form"
      onInput={() => setDismissedState(state)}
    >
      <label htmlFor="source_type">Type</label>
      <select
        key={selectKey}
        id="source_type"
        name="source_type"
        defaultValue={state.values.source_type}
        disabled={isPending}
      >
        <option value="text">Text</option>
        <option value="url">URL</option>
      </select>

      <label htmlFor="title">Title (optional)</label>
      <input
        id="title"
        name="title"
        maxLength={300}
        placeholder="What's on your mind?"
        defaultValue={state.values.title}
        readOnly={isPending}
        aria-invalid={titleError ? true : undefined}
        aria-describedby={titleError ? "title-error" : undefined}
      />
      {titleError && (
        <p id="title-error" className="field-error">
          {titleError}
        </p>
      )}

      <label htmlFor="content">Content</label>
      <textarea
        id="content"
        name="content"
        rows={5}
        required
        placeholder="Capture an idea, note, or link..."
        defaultValue={state.values.content}
        readOnly={isPending}
        aria-invalid={contentError ? true : undefined}
        aria-describedby={contentError ? "content-error" : undefined}
      />
      {contentError && (
        <p id="content-error" className="field-error">
          {contentError}
        </p>
      )}

      <button type="submit" disabled={isPending}>
        {isPending ? "Saving…" : "Save Capture"}
      </button>

      <div aria-live="polite">
        {showSuccess && (
          <p className="form-message form-success" role="status">
            {state.message}
          </p>
        )}
        {state.status === "error" && (
          <p className="form-message form-error" role="alert">
            {state.message}
          </p>
        )}
      </div>
    </form>
  );
}
