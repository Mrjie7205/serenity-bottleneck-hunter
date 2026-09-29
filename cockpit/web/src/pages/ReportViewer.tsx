import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api";

export default function ReportViewer() {
  const { file } = useParams<{ file: string }>();
  const nav = useNavigate();
  if (!file) return null;
  // Router parameters have already been URL-decoded, including literal '%' in filenames.
  const decoded = file;

  return (
    <div className="viewer">
      <div className="viewer-bar">
        <button className="back" onClick={() => nav("/library")}>
          ← 返回报告库
        </button>
        <span className="t">{decoded.replace(".html", "")}</span>
      </div>
      <iframe src={api.reportUrl(decoded)} title={decoded} sandbox="allow-scripts allow-popups" />
    </div>
  );
}
