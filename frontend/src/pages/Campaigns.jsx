import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ChannelBadge, StatusBadge } from "@/components/Badges";
import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import CampaignWizard from "./CampaignWizard";

export default function Campaigns() {
  const [campaigns, setCampaigns] = useState([]);
  const [open, setOpen] = useState(false);

  const load = () => api.get("/campaigns").then(r => setCampaigns(r.data));
  useEffect(() => { load(); const t = setInterval(load, 4000); return () => clearInterval(t); }, []);

  const del = async (id) => {
    if (!window.confirm("Delete campaign?")) return;
    await api.delete(`/campaigns/${id}`);
    toast.success("Deleted"); load();
  };

  return (
    <div className="space-y-4" data-testid="campaigns-page">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">Broadcast</div>
          <h1 className="text-3xl font-black tracking-tighter">Campaigns</h1>
        </div>
        <Button className="rounded-sm gap-2" onClick={() => setOpen(true)} data-testid="new-campaign-button">
          <Plus className="h-4 w-4" /> New Campaign
        </Button>
      </div>

      <Card className="rounded-sm shadow-none">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-muted/40">
              <tr className="text-left text-[10px] uppercase tracking-wider text-muted-foreground">
                <th className="px-3 py-2">Name</th>
                <th className="px-3 py-2">Channel</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2 text-right">Queued</th>
                <th className="px-3 py-2 text-right">Sent</th>
                <th className="px-3 py-2 text-right">Delivered</th>
                <th className="px-3 py-2 text-right">Failed</th>
                <th className="px-3 py-2 text-right">Replies</th>
                <th className="px-3 py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {campaigns.map(c => (
                <tr key={c.id} className="border-t border-border hover:bg-accent/40" data-testid={`campaign-row-${c.id}`}>
                  <td className="px-3 py-2 font-medium"><Link to={`/campaigns/${c.id}`} className="hover:underline" data-testid={`campaign-detail-link-${c.id}`}>{c.name}</Link></td>
                  <td className="px-3 py-2"><ChannelBadge channel={c.channel} /></td>
                  <td className="px-3 py-2"><StatusBadge status={c.status} /></td>
                  <td className="px-3 py-2 text-right font-mono">{c.stats?.queued ?? 0}</td>
                  <td className="px-3 py-2 text-right font-mono">{c.stats?.sent ?? 0}</td>
                  <td className="px-3 py-2 text-right font-mono">{c.stats?.delivered ?? 0}</td>
                  <td className="px-3 py-2 text-right font-mono">{c.stats?.failed ?? 0}</td>
                  <td className="px-3 py-2 text-right font-mono">{c.stats?.replied ?? 0}</td>
                  <td className="px-3 py-2 text-right">
                    <Button variant="ghost" size="sm" className="text-red-600 rounded-sm gap-1" onClick={() => del(c.id)} data-testid={`delete-campaign-${c.id}`}>
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </td>
                </tr>
              ))}
              {campaigns.length === 0 && <tr><td colSpan={9} className="text-center text-muted-foreground py-10">No campaigns yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </Card>

      <CampaignWizard open={open} onOpenChange={setOpen} onCreated={load} />
    </div>
  );
}
