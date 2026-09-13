import { Route, Routes } from "react-router-dom";

import { NAV_ITEMS } from "./nav";
import { AvatarFactory } from "./pages/AvatarFactory";
import { Avatars } from "./pages/Avatars";
import { ComingSoon } from "./pages/ComingSoon";
import { Dashboard } from "./pages/Dashboard";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Dashboard />} />
      <Route path="/avatars" element={<Avatars />} />
      <Route path="/avatars/:id/factory" element={<AvatarFactory />} />
      {NAV_ITEMS.filter((item) => !item.implemented).map((item) => (
        <Route
          key={item.path}
          path={item.path}
          element={<ComingSoon title={item.label} phase={item.phase} />}
        />
      ))}
    </Routes>
  );
}
