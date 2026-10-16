"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { ShieldIcon } from "@/components/ui";
import { getToken } from "@/lib/auth";

export default function Home() {
  const router = useRouter();
  useEffect(() => {
    getToken().then((t) => {
      if (t) router.replace("/chat");
    });
  }, [router]);

  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-6 text-center">
      <ShieldIcon className="h-10 w-10 text-white" />
      <h1 className="mt-6 max-w-2xl text-4xl font-semibold tracking-tight text-white sm:text-5xl">
        Your agent handles the money. You approve what can&apos;t be undone.
      </h1>
      <p className="mt-5 max-w-xl text-lg text-white/60">
        Warden watches a parent&apos;s accounts for scams and odd charges, keeps bills on track, and never pays or cancels
        anything without a family member&apos;s OK.
      </p>
      <Link href="/login" className="mt-10 inline-flex min-h-12 items-center rounded-full bg-white px-8 text-lg font-medium text-black">
        Sign in
      </Link>
    </main>
  );
}
