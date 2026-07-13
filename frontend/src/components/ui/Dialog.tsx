import React, { useState } from 'react';
import ReactDOM from 'react-dom';
import { Button } from './Button';
import './Dialog.css';

export interface DialogProps {
  isOpen: boolean;
  title: string;
  message: string;
  inputPlaceholder?: string;
  onConfirm: (inputValue?: string) => void;
  onCancel: () => void;
  confirmText?: string;
  cancelText?: string;
}

export const Dialog: React.FC<DialogProps> = ({
  isOpen,
  title,
  message,
  inputPlaceholder,
  onConfirm,
  onCancel,
  confirmText = 'Confirm',
  cancelText = 'Cancel'
}) => {
  const [inputValue, setInputValue] = useState('');

  if (!isOpen) return null;

  return ReactDOM.createPortal(
    <div className="dialog-overlay" onClick={onCancel}>
      <div className="dialog-container animate-fade-in" onClick={e => e.stopPropagation()}>
        <h3 className="dialog-title">{title}</h3>
        <p className="dialog-message">{message}</p>
        
        {inputPlaceholder !== undefined && (
          <textarea
            className="dialog-input"
            placeholder={inputPlaceholder}
            value={inputValue}
            onChange={e => setInputValue(e.target.value)}
            rows={4}
            autoFocus
          />
        )}
        
        <div className="dialog-actions">
          <Button variant="secondary" onClick={onCancel}>{cancelText}</Button>
          <Button variant="primary" onClick={() => {
            onConfirm(inputPlaceholder !== undefined ? inputValue : undefined);
            setInputValue('');
          }}>
            {confirmText}
          </Button>
        </div>
      </div>
    </div>,
    document.body
  );
};
