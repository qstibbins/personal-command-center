"use client";

type SignOutButtonProps = {
  signOutAction: () => Promise<void>;
};

export function SignOutButton({ signOutAction }: SignOutButtonProps) {
  return (
    <form action={signOutAction}>
      <button type="submit" className="sign-out-button">
        Sign out
      </button>
    </form>
  );
}
