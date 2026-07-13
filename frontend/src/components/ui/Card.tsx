import React from 'react';
import './Card.css';

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  padding?: 'none' | 'sm' | 'md' | 'lg';
  interactive?: boolean;
}

export const Card = React.forwardRef<HTMLDivElement, CardProps>(
  ({ className = '', padding = 'md', interactive = false, children, ...props }, ref) => {
    
    const baseClass = "card";
    const paddingClass = `card-padding-${padding}`;
    const interactiveClass = interactive ? 'card-interactive' : '';
    
    return (
      <div
        ref={ref}
        className={`${baseClass} ${paddingClass} ${interactiveClass} ${className}`}
        {...props}
      >
        {children}
      </div>
    );
  }
);
Card.displayName = 'Card';
