"use client";

import { useState, useEffect, type ReactNode } from "react";

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
  const [activeTab, setActiveTab] = useState(defaultTab);

  useEffect(() => {
    const hash = window.location.hash.replace("#", "");
    if (hash && tabs.some((t) => t.id === hash)) {
      setActiveTab(hash);
    }

    const onHashChange = () => {
      const h = window.location.hash.replace("#", "");
      if (h && tabs.some((t) => t.id === h)) {
        setActiveTab(h);
      }
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, [tabs]);

  const handleTabClick = (id: string) => {
    setActiveTab(id);
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

      {tabs.map((tab) => (
        <div key={tab.id} className={activeTab === tab.id ? "block" : "hidden"}>
          {tab.content}
        </div>
      ))}
    </div>
  );
}
