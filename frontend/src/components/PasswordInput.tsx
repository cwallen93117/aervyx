"use client";

import { useState, type CSSProperties, type InputHTMLAttributes } from "react";

type PasswordInputProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & {
  inputStyle?: CSSProperties;
  wrapperClassName?: string;
  wrapperStyle?: CSSProperties;
};

function EyeIcon({ hidden }: { hidden: boolean }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="M2.25 12s3.5-6.25 9.75-6.25S21.75 12 21.75 12s-3.5 6.25-9.75 6.25S2.25 12 2.25 12Z" />
      <circle cx="12" cy="12" r="2.75" />
      {hidden ? null : <path className="password-toggle-slash" d="M4 4l16 16" />}
    </svg>
  );
}

export function PasswordInput({
  className,
  inputStyle,
  wrapperClassName,
  wrapperStyle,
  ...inputProps
}: PasswordInputProps) {
  const [visible, setVisible] = useState(false);
  const label = visible ? "Hide password" : "Show password";
  const mergedInputStyle = inputStyle
    ? { ...inputStyle, paddingRight: inputStyle.paddingRight ?? 42 }
    : undefined;

  return (
    <div className={`password-input-wrap${wrapperClassName ? ` ${wrapperClassName}` : ""}`} style={wrapperStyle}>
      <input
        {...inputProps}
        className={className}
        style={mergedInputStyle}
        type={visible ? "text" : "password"}
      />
      <button
        type="button"
        className="password-visibility-toggle"
        aria-label={label}
        title={label}
        aria-pressed={visible}
        onClick={() => setVisible((current) => !current)}
      >
        <EyeIcon hidden={!visible} />
      </button>
    </div>
  );
}
