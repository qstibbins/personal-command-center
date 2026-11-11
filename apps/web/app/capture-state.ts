export type CaptureFieldErrors = {
  title?: string;
  content?: string;
};

export type CaptureFormState = {
  status: "idle" | "success" | "error";
  message: string | null;
  fieldErrors?: CaptureFieldErrors;
  values: {
    source_type: string;
    title: string;
    content: string;
  };
};

export const initialCaptureState: CaptureFormState = {
  status: "idle",
  message: null,
  values: { source_type: "text", title: "", content: "" },
};
