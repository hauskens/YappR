// Global type declarations for vendor libraries

declare global {
  interface Window {
    htmx: {
      trigger: (element: string | Element, event: string) => void;
      on: (event: string, handler: (evt: any) => void) => void;
      ajax: (method: string, url: string, options?: any) => void;
      process: (element: Element) => void;
      [key: string]: any;
    };
    bootstrap: {
      Modal: new (element: Element, options?: any) => {
        show: () => void;
        hide: () => void;
        dispose: () => void;
      };
      Tooltip: new (element: Element, options?: any) => {
        show: () => void;
        hide: () => void;
        dispose: () => void;
      };
      Popover: new (element: Element, options?: any) => {
        show: () => void;
        hide: () => void;
        dispose: () => void;
      };
      [key: string]: any;
    };
  }
}

export {};