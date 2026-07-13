import React from 'react';
import './Badge.css';

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  color?: 'red' | 'blue' | 'green' | 'yellow' | 'gray';
}

export const Badge = React.forwardRef<HTMLSpanElement, BadgeProps>(
  ({ className = '', color = 'gray', children, ...props }, ref) => {
    
    const baseClass = "badge";
    const colorClass = `badge-${color}`;
    
    return (
      <span
        ref={ref}
        className={`${baseClass} ${colorClass} ${className}`}
        {...props}
      >
        {children}
      </span>
    );
  }
);
Badge.displayName = 'Badge';
