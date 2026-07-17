import CssBaseline from "@mui/material/CssBaseline";
import {ThemeProvider} from "@mui/material/styles";

import PlannerPage from "./pages/PlannerPage";
import {plannerTheme} from "./theme";

function App() {
    return (
        <ThemeProvider theme={plannerTheme}>
            <CssBaseline />
            <PlannerPage />
        </ThemeProvider>
    );
}

export default App;
