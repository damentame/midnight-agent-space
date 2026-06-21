type Props = {
  className?: string;
};

export default function Spinner({ className = "h-4 w-4" }: Props) {
  return (
    <span
      className={`inline-block shrink-0 rounded-full border-2 border-current border-t-transparent animate-spin ${className}`}
      aria-hidden
    />
  );
}
