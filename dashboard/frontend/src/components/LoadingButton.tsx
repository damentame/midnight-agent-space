import type { ButtonHTMLAttributes, ReactNode } from "react";
import Spinner from "./Spinner";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  loading?: boolean;
  loadingLabel?: ReactNode;
};

export default function LoadingButton({
  loading = false,
  loadingLabel,
  children,
  className = "",
  disabled,
  ...props
}: Props) {
  const isDisabled = Boolean(disabled) || loading;
  return (
    <button
      type="button"
      {...props}
      disabled={isDisabled}
      aria-busy={loading}
      className={`inline-flex items-center justify-center gap-2 ${loading ? "cursor-wait" : ""} ${className}`}
    >
      {loading && <Spinner className="h-3.5 w-3.5" />}
      <span>{loading ? (loadingLabel ?? children) : children}</span>
    </button>
  );
}
