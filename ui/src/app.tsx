import { BrowserRouter } from "react-router-dom";
import { AppRouter } from "./router";
import { Shell } from "./components/common/Shell";
import { ToastProvider } from "./components/common/Toast";

export default function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <Shell>
          <AppRouter />
        </Shell>
      </ToastProvider>
    </BrowserRouter>
  );
}
