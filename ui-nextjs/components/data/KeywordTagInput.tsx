'use client';

import { useState, useRef, KeyboardEvent, ClipboardEvent } from 'react';

interface KeywordTagInputProps {
  value: string[];
  onChange: (keywords: string[]) => void;
}

export default function KeywordTagInput({ value, onChange }: KeywordTagInputProps) {
  const [input, setInput] = useState('');
  const [flashTag, setFlashTag] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const addKeywords = (raw: string) => {
    const newKeywords = raw
      .split(',')
      .map((k) => k.trim())
      .filter(Boolean);

    const unique: string[] = [];
    for (const kw of newKeywords) {
      if (value.includes(kw)) {
        // Flash duplicate briefly
        setFlashTag(kw);
        setTimeout(() => setFlashTag(null), 400);
      } else if (!unique.includes(kw)) {
        unique.push(kw);
      }
    }

    if (unique.length > 0) {
      onChange([...value, ...unique]);
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      if (input.trim()) {
        addKeywords(input);
        setInput('');
      }
    } else if (e.key === 'Backspace' && !input && value.length > 0) {
      onChange(value.slice(0, -1));
    }
  };

  const handlePaste = (e: ClipboardEvent<HTMLInputElement>) => {
    const pasted = e.clipboardData.getData('text');
    if (pasted.includes(',')) {
      e.preventDefault();
      addKeywords(pasted);
      setInput('');
    }
  };

  const removeTag = (keyword: string) => {
    onChange(value.filter((k) => k !== keyword));
  };

  return (
    <div
      className="flex flex-wrap gap-1.5 px-3 py-2 bg-[#292929] border border-[#404040] rounded cursor-text focus-within:border-[#00ff32]"
      onClick={() => inputRef.current?.focus()}
    >
      {value.map((keyword) => (
        <span
          key={keyword}
          className={`inline-flex items-center gap-1 bg-[#404040] text-gray-300 rounded-full px-2.5 py-1 text-sm transition-colors ${
            flashTag === keyword ? 'bg-yellow-800/60' : ''
          }`}
        >
          {keyword}
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              removeTag(keyword);
            }}
            className="text-gray-500 hover:text-white transition-colors ml-0.5"
          >
            &times;
          </button>
        </span>
      ))}
      <input
        ref={inputRef}
        type="text"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        onPaste={handlePaste}
        placeholder={value.length === 0 ? 'Type keyword and press Enter' : ''}
        className="flex-1 min-w-[120px] bg-transparent text-white text-sm placeholder-gray-600 outline-none"
      />
    </div>
  );
}
