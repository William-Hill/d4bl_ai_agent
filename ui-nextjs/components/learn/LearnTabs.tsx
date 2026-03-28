"use client";

import { useState, useEffect, useMemo, type ReactNode } from "react";

interface Tab {
  id: string;
  label: string;
  content: ReactNode;
}

interface LearnTabsProps {
  tabs: Tab[];
  defaultTab?: string;
}

export default function LearnTabs({ tabs, defaultTab = "compare" }: LearnTabsProps) {
  const tabIds = useMemo(() => tabs.map((t) => t.id), [tabs]);
  const [activeTab, setActiveTab] = useState(defaultTab);
  // Track which tabs have been visited so we mount lazily but keep mounted
  const [mounted, setMounted] = useState<Set<string>>(() => new Set([defaultTab]));

  useEffect(() => {
    const applyHash = (h: string) => {
      if (h && tabIds.includes(h)) {
        setActiveTab(h);
        setMounted((prev) => (prev.has(h) ? prev : new Set([...prev, h])));
      }
    };

    // Read hash on mount (client-only) via microtask to satisfy lint rule
    const initialHash = window.location.hash.replace("#", "");
    queueMicrotask(() => applyHash(initialHash));

    const onHashChange = () => {
      applyHash(window.location.hash.replace("#", ""));
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, [tabIds]);

  const handleTabClick = (id: string) => {
    setActiveTab(id);
    setMounted((prev) => (prev.has(id) ? prev : new Set([...prev, id])));
    window.history.replaceState(null, "", `#${id}`);
  };

  return (
    <div>
      <div className="flex border-b border-[#404040] mb-8">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => handleTabClick(tab.id)}
            className={`px-6 py-3 text-sm font-medium transition-colors ${
              activeTab === tab.id
                ? "border-b-2 border-[#00ff32] text-[#00ff32]"
                : "text-gray-400 hover:text-gray-200"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {tabs.map((tab) =>
        mounted.has(tab.id) ? (
          <div key={tab.id} className={activeTab === tab.id ? "block" : "hidden"}>
            {tab.content}
          </div>
        ) : null
      )}
    </div>
  );
}
