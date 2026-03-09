'use client';

import Link from 'next/link';
import { useAuth } from '@/lib/auth-context';

export default function NavBar() {
  const { user, role, isAdmin, signOut } = useAuth();

  return (
    <nav className="border-b border-[#404040] bg-[#1a1a1a] px-6 py-3 flex items-center gap-8">
      <span className="font-bold text-[#00ff32] text-lg tracking-tight">D4BL</span>
      <Link href="/" className="text-sm text-gray-300 hover:text-[#00ff32] transition-colors">
        Research
      </Link>
      <Link href="/explore" className="text-sm text-gray-300 hover:text-[#00ff32] transition-colors">
        Explore Data
      </Link>
      {isAdmin && (
        <Link href="/data" className="text-sm text-gray-300 hover:text-[#00ff32] transition-colors">
          Data
        </Link>
      )}
      {isAdmin && (
        <Link href="/admin" className="text-sm text-gray-300 hover:text-[#00ff32] transition-colors">
          Admin
        </Link>
      )}
      <div className="ml-auto flex items-center gap-4">
        {user && (
          <>
            <span className="text-sm text-gray-400">{user.email}</span>
            {role && (
              <span className="text-xs px-2 py-0.5 rounded bg-[#404040] text-gray-300">
                {role}
              </span>
            )}
            <button
              onClick={signOut}
              className="text-sm text-gray-400 hover:text-red-400 transition-colors"
            >
              Sign out
            </button>
          </>
        )}
      </div>
    </nav>
  );
}
