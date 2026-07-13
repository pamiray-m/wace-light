import React from "react";
import { createRoot } from "react-dom/client";
import { VoundryApp } from "./App";

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <VoundryApp />
  </React.StrictMode>,
);
