'use client';

import { useState, FormEvent } from 'react';
import { useAuth } from '@/lib/auth-context';
import { API_BASE } from '@/lib/api';

interface FormData {
  title: string;
  description: string;
  who_benefits: string;
  example: string;
}

const EMPTY_FORM: FormData = {
  title: '',
  description: '',
  who_benefits: '',
  example: '',
};

export default function FeatureRequestForm() {
  const { session } = useAuth();
  const [form, setForm] = useState<FormData>(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>
  ) => {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setSuccess(null);
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/api/admin/uploads/feature-request`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(session?.access_token
            ? { Authorization: `Bearer ${session.access_token}` }
            : {}),
        },
        body: JSON.stringify(form),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data?.detail ?? `Request failed (${res.status})`);
      }

      setSuccess('Feature request submitted — thank you!');
      setForm(EMPTY_FORM);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Submission failed');
    } finally {
      setSubmitting(false);
    }
  };

  const inputClass =
    'w-full bg-[#111111] border border-[#404040] rounded px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-[#00ff32] transition-colors';
  const labelClass = 'block text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1';

  return (
    <form onSubmit={handleSubmit} className="space-y-4 mt-4">
      <div>
        <label htmlFor="feat-title" className={labelClass}>
          What feature would you like? <span className="text-red-400">*</span>
        </label>
        <input
          id="feat-title"
          name="title"
          type="text"
          required
          value={form.title}
          onChange={handleChange}
          placeholder="e.g. Export chart as PNG"
          className={inputClass}
        />
      </div>

      <div>
        <label htmlFor="feat-description" className={labelClass}>
          Describe the feature <span className="text-red-400">*</span>
        </label>
        <textarea
          id="feat-description"
          name="description"
          required
          rows={4}
          value={form.description}
          onChange={handleChange}
          placeholder="What should it do? How should it work?"
          className={inputClass}
        />
      </div>

      <div>
        <label htmlFor="feat-who" className={labelClass}>
          Who benefits from this? <span className="text-red-400">*</span>
        </label>
        <input
          id="feat-who"
          name="who_benefits"
          type="text"
          required
          value={form.who_benefits}
          onChange={handleChange}
          placeholder="e.g. Researchers, community organizers, policy staff"
          className={inputClass}
        />
      </div>

      <div>
        <label htmlFor="feat-example" className={labelClass}>
          Example of how it would work{' '}
          <span className="text-gray-600">(optional)</span>
        </label>
        <textarea
          id="feat-example"
          name="example"
          rows={3}
          value={form.example}
          onChange={handleChange}
          placeholder="Walk through a specific scenario..."
          className={inputClass}
        />
      </div>

      {success && (
        <p className="text-[#00ff32] text-sm font-medium">{success}</p>
      )}
      {error && (
        <p className="text-red-400 text-sm font-medium">{error}</p>
      )}

      <button
        type="submit"
        disabled={submitting}
        className="px-5 py-2 rounded bg-[#00ff32] text-black text-sm font-semibold hover:bg-[#00cc28] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {submitting ? 'Submitting…' : 'Submit Request'}
      </button>
    </form>
  );
}
