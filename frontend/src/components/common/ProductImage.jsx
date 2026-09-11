import { useState } from "react";
import { ImageOff } from "lucide-react";

export function ProductImage({ src, alt = "", className = "", ...props }) {
  const [failedSource, setFailedSource] = useState(null);
  if (!src || failedSource === src) {
    return (
      <div className={`flex items-center justify-center bg-gray-100 text-gray-400 ${className}`} role="img" aria-label={alt || "Product image unavailable"}>
        <ImageOff size={32} aria-hidden="true" />
      </div>
    );
  }
  return <img {...props} src={src} alt={alt} className={className} loading="lazy" onError={() => setFailedSource(src)} />;
}
