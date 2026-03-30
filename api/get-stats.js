const { MongoClient } = require('mongodb');

const uri = "mongodb+srv://Alexgaming:Alex27Junio@cluster0.55a5siw.mongodb.net/?retryWrites=true&w=majority";

export default async function handler(req, res) {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Cache-Control', 'no-store, max-age=0');

    const client = new MongoClient(uri);
    try {
        await client.connect();
        const db = client.db("flexus_data");
        const stats = await db.collection("ads_stats").findOne({ id: "global" });
        res.status(200).json({ views: stats ? stats.views : 0 });
    } catch (e) {
        res.status(500).json({ error: e.message });
    } finally {
        await client.close();
    }
}
