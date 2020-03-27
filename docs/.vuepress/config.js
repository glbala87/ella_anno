module.exports = {
    title: 'anno documentation',
    base: '/anno-docs/',

    head: [['link', { rel: 'shortcut icon', type: 'image/x-icon', href: `./favicon.png` }]],

    themeConfig: {
        lastUpdated: 'Last Updated', // string | boolean

        nav: [
            { text: 'Home', link: '/' },
            { text: 'Technical documentation', link: '/technical/' },
            { text: 'Release notes', link: '/releasenotes/' },
            { text: 'allel.es', link: 'http://allel.es' }
        ],

        sidebarDepth: 2,

        sidebar: {
            '/technical/': [
                {
                    title: 'Technical documentation',
                    collapsable: false,
                    children: [
                        '/technical/',
                        '/technical/setup', 
                        '/technical/annotation',
                        '/technical/sysinternals' 
                    ]
                }
            ],
            '/releasenotes/': [
                {
                    title: 'Release notes',
                    collapsable: false,
                    children: [
                        '/releasenotes/',
                        '/releasenotes/olderreleases'
                    ]
                }
            ]
        }
    }
}
