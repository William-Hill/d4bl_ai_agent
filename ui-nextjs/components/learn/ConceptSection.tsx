'use client';

import { useEffect, useRef, useState } from 'react';

interface Props {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}

export default function ConceptSection({ title, subtitle, children }: Props) {
  const ref = useRef<HTMLElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer.unobserve(el);
        }
      },
      { threshold: 0.1 }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <section
      ref={ref}
      className={`max-w-4xl mx-auto px-6 py-24 motion-safe:transition-all motion-safe:duration-700 motion-safe:ease-out ${
        visible ? 'opacity-100 translate-y-0' : 'motion-safe:opacity-0 motion-safe:translate-y-5'
      }`}
    >
      <h2 className="text-3xl font-bold text-white mb-2">{title}</h2>
      {subtitle && (
        <p className="text-lg text-gray-400 mb-8">{subtitle}</p>
      )}
      <div className="text-gray-300 leading-relaxed space-y-4">{children}</div>
    </section>
  );
}
