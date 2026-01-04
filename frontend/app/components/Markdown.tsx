"use client";

import ReactMarkdown from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";

const components: Components = {
  a: ({ href, children, ...props }) => (
    <a href={href ?? ""} target="_blank" rel="noreferrer" {...props}>
      {children}
    </a>
  )
};

export function Markdown({ content, className }: { content: string; className?: string }) {
  return (
    <ReactMarkdown className={className} remarkPlugins={[remarkGfm, remarkBreaks]} components={components}>
      {content}
    </ReactMarkdown>
  );
}
