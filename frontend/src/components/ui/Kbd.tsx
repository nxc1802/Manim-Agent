import React from 'react';
import './Kbd.css';

interface KbdProps extends React.HTMLAttributes<HTMLElement> {}

export const Kbd = React.forwardRef<HTMLElement, KbdProps>(
  ({ className = '', children, ...props }, ref) => {
    return (
      <kbd
        ref={ref}
        className={`kbd ${className}`}
        {...props}
      >
        {children}
      </kbd>
    );
  }
);
Kbd.displayName = 'Kbd';
