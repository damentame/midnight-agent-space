import Spinner from "./Spinner";

type Props = {
  message: string;
};

export default function WorkingBanner({ message }: Props) {
  return (
    <div
      className="rounded-lg border border-orange-200 bg-orange-50 px-4 py-3 flex items-center gap-3 text-sm text-orange-900"
      role="status"
      aria-live="polite"
    >
      <Spinner className="h-4 w-4 text-orange-600" />
      <span className="font-medium">{message}</span>
    </div>
  );
}
