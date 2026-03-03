import clsx from "clsx";

interface Props {
  status: "pending" | "approved" | "declined";
  onApprove: () => void;
  onDecline: () => void;
}

export default function ConfirmBar({ status, onApprove, onDecline }: Props) {
  if (status !== "pending") {
    return (
      <div
        className={clsx(
          "rounded-lg border px-3 py-2 text-xs font-medium",
          status === "approved"
            ? "border-green-500/30 bg-green-500/10 text-green-400"
            : "border-gray-600 bg-gray-800 text-gray-400",
        )}
      >
        {status === "approved" ? "Approved — action executed" : "Declined — action skipped"}
      </div>
    );
  }

  return (
    <div className="flex items-center gap-3 rounded-lg border border-yellow-500/30 bg-yellow-500/10 px-3 py-2">
      <span className="text-xs text-yellow-300">
        This action requires your confirmation.
      </span>
      <div className="ml-auto flex gap-2">
        <button
          onClick={onApprove}
          className="rounded-md bg-green-600 px-3 py-1 text-xs font-medium text-white hover:bg-green-500 transition-colors"
        >
          Approve
        </button>
        <button
          onClick={onDecline}
          className="rounded-md bg-gray-700 px-3 py-1 text-xs font-medium text-gray-300 hover:bg-gray-600 transition-colors"
        >
          Decline
        </button>
      </div>
    </div>
  );
}
