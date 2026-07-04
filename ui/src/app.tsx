import { BrowserRouter } from "react-router-dom";
import { AppRouter } from "./router";
import { Shell } from "./components/common/Shell";

export default function App() {
  return (
    <BrowserRouter>
      <Shell>
        <AppRouter />
      </Shell>
    </BrowserRouter>
  );
}
