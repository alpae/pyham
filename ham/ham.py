from xml.etree.ElementTree import XMLParser
from . import taxonomy as tax
from . import genome
from .TreeProfile import TreeProfile
from ham import parsers
from ham import mapper
import logging
from . import abstractgene
import copy

logger = logging.getLogger(__name__)


class ParserFilter(object):
    """
    Object containing a list of queries (hogs/genes ids) that will be used by the FilterOrthoXMLParser to collect
    in the orthoxml file the required information for the OrthoXMLParser to only parse data related to this sub-dataset
    of interest.

    The ParserFilter first collect top level HOG ids, unique or external genes ids that are related to the hogs of
    interest (FilterOrthoXMLParser queries) then run the FilterOrthoXMLParser to built the list of all genes and hogs
    (OrthoXMLParser queries) required to be able to work on this subset.

    Attributes:
        HOGId_filter (:obj:`set`): :obj:`set` of HOG ids used by the FilterOrthoXMLParser.
        GeneExtId_filter (:obj:`set`): :obj:`set` of external genes ids used by the FilterOrthoXMLParser.
        GeneIntId_filter (:obj:`set`): :obj:`set` of unique genes ids used by the FilterOrthoXMLParser.

        geneUniqueId (:obj:`set`): :obj:`set` of all required unique gene ids build by the FilterOrthoXMLParser.
        hogsId (:obj:`set`): :obj:`set` of all required top level hog ids build by the FilterOrthoXMLParser.
    """

    def __init__(self):

        # Information used to select a subdataset of interest during the applyFilter call.
        self.HOGId_filter = set()
        self.GeneExtId_filter = set()
        self.GeneIntId_filter = set()

        # Information created during buildFilter call that is required by the main OrthoXMLParser for the HOGs
        # construction during HAM instantiation.
        self.geneUniqueId = None  # [geneUniqueIds]
        self.hogsId = None  # [hogIds]

    def add_hogs_via_hogId(self, list_id):
        self.HOGId_filter = self.HOGId_filter | set(map(lambda x: str(x), list_id))

    def add_hogs_via_GeneExtId(self, list_id):
        self.GeneExtId_filter = self.GeneExtId_filter | set(map(lambda x: str(x), list_id))

    def add_hogs_via_GeneIntId(self, list_id):
        self.GeneIntId_filter = self.GeneIntId_filter | set(map(lambda x: str(x), list_id))

    def buildFilter(self, file_object, type_hog_file="orthoxml"):
        """ This function will use the FilterOrthoXMLParser with the *_filter queries to build geneUniqueId and
        hogsId.

        Args:
            hog_file (:obj:`str`): Path to the file that contained the HOGs information.
            type_hog_file (:obj:`str`):  File type of the hog_file. Can be "orthoxml or "hdf5". Defaults to "orthoxml".
        """

        if type_hog_file == "orthoxml":
            self.geneUniqueId, self.hogsId = self._filter_hogs_and_genes(file_object)
        elif type_hog_file == "hdf5":
            pass

        else:
            raise TypeError("Invalid type of hog file.")

    def _filter_hogs_and_genes(self, file_object):

        """ This function collect from an orthoxml file all data that is required to build HAM object based this filter
            object.

            Args:
                file_object (:obj:`FileObject`): File Object of the orthoxml to parse.

            Returns:
                :obj:`set` of gene unique ids, :obj:`set` of top level hog id.

        """

        factory_filter = parsers.FilterOrthoXMLParser(self)
        parser_filter = XMLParser(target=factory_filter)

        for line in file_object:
            parser_filter.feed(line)

        return set(factory_filter.geneUniqueId), set(factory_filter.hogsId)


class HAM(object):
    """
    [Add here description of HAM]
    
    Attributes:
        hog_file (:obj:`str`): Path to the file that contained the HOGs information.
        hog_file_type (:obj:`str`): File type of the hog_file. Can be "orthoxml or "hdf5". Defaults to "orthoxml".
        top_level_hogs (:obj:`dict`): Dictionary that map hog unique id with its list of related :obj:`HOG`.
        extant_gene_map (:obj:`dict`): Dictionary that map gene unique id with its list of related :obj:`Gene`.
        external_id_mapper (:obj:`dict`): Dictionary that map a gene external id with its list of related :obj:`HOG` or :obj:`Gene`.
        HOGMaps (:obj:`dict`): Dictionary that map a :obj:`frozenset` of a pair of genomes to its :obj:`HOGsMap`.
        filter_obj (:obj:`ParserFilter`): :obj:`ParserFilter` used during the instanciation of HAM. Defaults to None.
        taxonomy: (:obj:`Taxonomy`): :obj:`Taxonomy` build and used by :obj:`HAM` instance.

    """

    def __init__(self, newick_str, hog_file, type_hog_file="orthoxml", filter_object=None, use_internal_name=False):
        """

        Args:
            newick_str (:obj:`str`): Newick str used to build the taxonomy.
            hog_file (:obj:`str`): Path to the file that contained the HOGs information.
            type_hog_file (:obj:`str`, optional): File type of the hog_file. Can be "orthoxml or "hdf5". Defaults
            to "orthoxml".
            filter_object (:obj:`ParserFilter`, optional): :obj:`ParserFilter` used during the instantiation of HAM.
            Defaults to None.
            use_internal_name (:obj:`Boolean`, optional): Set to decide to use or not the internal naming of the given 
            newick string. This should be set to False when support values are provided in the newick. Defaults to False.
        """

        # HOGs file
        self.hog_file = hog_file
        self.hog_file_type = type_hog_file

        # Filtering
        if isinstance(filter_object, ParserFilter) or filter_object is None:
            self.filter_obj = filter_object
        else:
            raise TypeError("filter_obj should be '{}', got {}"
                            .format(ParserFilter.__name__,
                                    type(filter_object).__name__))

        # Taxonomy
        self.taxonomy = tax.Taxonomy(newick_str, use_internal_name=use_internal_name)
        logger.info('Build taxonomy: completed.')

        # Misc. information
        self.top_level_hogs = None
        self.extant_gene_map = None
        self.external_id_mapper = None
        self.HOGMaps = {}

        # Parsing of data
        if self.hog_file_type == "orthoxml":

            #  If filter_object specified, ham parse a first time to collect required information
            if self.filter_obj is not None:
                with open(self.hog_file, 'r') as orthoxml_file:
                    self.filter_obj.buildFilter(orthoxml_file, self.hog_file_type)
                    logger.info(
                        'Filtering Indexing of Orthoxml done: {} top level hogs and {} extant genes will be extract.'.format(
                            len(self.filter_obj.hogsId),
                            len(self.filter_obj.geneUniqueId)))

            # This is the actual parser to build HOG/Gene and related Genomes.
            with open(self.hog_file, 'r') as orthoxml_file:
                self.top_level_hogs, self.extant_gene_map, self.external_id_mapper = \
                    self._build_hogs_and_genes(orthoxml_file, filter_object=self.filter_obj)

            logger.info(
                'Parse Orthoxml: {} top level hogs and {} extant genes extract.'.format(len(self.top_level_hogs),
                                                                                        len(
                                                                                            self.extant_gene_map)))

        elif self.hog_file_type == "hdf5":
            # Looping through all orthoXML within the hdf5
            #   for each run self.build_...
            #       update self.top_level_hogs and self.extant_gene_map for each
            pass

        else:
            raise TypeError("Invalid type of hog file")

        logger.info(
            'Set up HAM analysis: ready to go with {} hogs founded within {} species.'.format(
                len(self.top_level_hogs), len(self.taxonomy.leaves)))

    # ... TOOLS ... #

    def compare_genomes_vertically(self, genomes_set):

        """
        Function to compute a :obj:`MapVertical` based on the 2 given genomes.

        Attributes:
            genomes_set (:obj:`set`): set of 2 :obj:`Genome`.

        Returns:
            :obj:`MapVertical`.
        
        Raises:
            TypeError: if there is not two genomes.
        """

        if len(genomes_set) != 2:
            raise TypeError(
                "{} genomes given for vertical HOG mapping, only 2 should be given".format(len(genomes_set)))

        vertical_map = mapper.MapVertical(self)
        vertical_map.add_map(self._get_HOGMap(genomes_set))

        return vertical_map

    def compare_genomes_lateral(self, genomes_set):

        """
        Function to compute a :obj:`MapLateral` based on given genomes set.

        Attributes:
            genomes_set (:obj:`set`): set of :obj:`Genome`.

        Returns:
            :obj:`MapLateral`.

        Raises:
            TypeError: if there is less than 2 genomes.
        """

        if len(genomes_set) < 2:
            raise TypeError(
                "{} genomes given for lateral HOG mapping, at least 2 should be given".format(len(genomes_set)))

        lateral_map = mapper.MapLateral(self)
        anc, desc = self._get_ancestor_and_descendant(copy.copy(genomes_set))
        for g in desc:
            hogmap = mapper.HOGsMap(self, {g, anc})
            lateral_map.add_map(hogmap)

        return lateral_map

    def create_hog_visualisation(self, hog, outfile=None):

        """
        Function to compute a :obj:`Hogvis`.

        If an outfile is specified, export the :obj:`Hogvis` as html file.

        Attributes:
            hog (:obj:`HOG`): HOG use as template for the :obj:`Hogvis`.
            outfile (:obj:`str`, optional): Path to the Hogvis html file.

        Returns:
            :obj:`Hogvis` 
        """

        newick_tree =self.taxonomy.get_newick_from_tree(hog.genome.taxon)

        vis = hog.get_hog_vis(newick_tree)

        if outfile is not None:
            with open(outfile, 'w') as fh:
                fh.write(vis.renderHTML)

        return vis

    def create_tree_profile(self, hog=None, outfile=None, export_with_histogram=True):

        """
        Function to compute a :obj:`TreeProfile`.
        
        If no hog are given the tree profile will be created for the whole HAM setup (all internal nodes with all HOGs).
        Otherwise, the tree profile is build for the specific hog given.
        
        If an outfile is specified, export the create_tree_profile as image into file.

        Attributes:
            hog (:obj:`HOG`, optional): HOG use as template for the create_tree_profile.
            outfile (:obj:`str`, optional): Path to the create_tree_profile output image file. valid extensions are .SVG, .PDF, .PNG.  
            export_with_histogram (:obj:`Bool`, optional): If True, export image with histogram at each internal node otherwise 
            display internal node information as text.

        Returns:
            :obj:`TreeProfile` 
        """

        tp = TreeProfile(self, hog=hog)

        if outfile:
            tp.export(outfile, display_internal_histogram=export_with_histogram)

        return tp

    def get_ascii_taxonomy(self):
        return self.taxonomy.tree.get_ascii()

    # ... QUERY METHODS ... #

    # ___ Gene ___ #

    def get_gene_by_id(self, gene_unique_id):

        """  Get the :obj:`Gene` that match the query unique gene Id.

            Args:
                gene_unique_id (:obj:`str` or :obj:`int`): Unique gene Id.

            Returns:
                :obj:`Gene` or raise KeyError

        """
        gene_unique_id = str(gene_unique_id)

        if gene_unique_id in self.extant_gene_map.keys():
            return self.extant_gene_map[gene_unique_id]

        raise KeyError('Id {} cannot match any Gene unique Id.'.format(gene_unique_id))

    def get_genes_by_external_id(self, external_gene_id):

        """  Get the list of :obj:`Gene` that match the query external gene Id.

            Args:
                external_gene_id (:obj:`str` or :obj:`int`): External gene Id.

            Returns:
                a list of :obj:`Gene` or raise KeyError

        """

        external_gene_id = str(external_gene_id)

        if external_gene_id in self.external_id_mapper.keys():
            return [self.extant_gene_map[qgene_id] for qgene_id in self.external_id_mapper[external_gene_id]]

        raise KeyError('Id {} cannot match any Gene external Id.'.format(external_gene_id))

    def get_list_extant_genes(self):

        """  Get the list of all :obj:`Gene`.

            Returns:
                a list of :obj:`Gene`.

        """

        return list(self.extant_gene_map.values())

    def get_dict_extant_genes(self):

        """  Get a dictionary that map all unique gene id with their related :obj:`Gene`.

            Returns:
                a dictionary mapping unique gene Id (:obj:`str`) with :obj:`Gene`.

        """

        return self.extant_gene_map

    # ___ HOG ___ #

    def get_hog_by_id(self, hog_id):

        """ Get the top level :obj:`HOG` that match the hog id query.

            Args:
                hog_id (:obj:`str` or :obj:`int`): Top level HOG id.

            Returns:
                :obj:`HOG` or raise KeyError

        """

        hog_id = str(hog_id)

        if hog_id in self.top_level_hogs.keys():
            return self.top_level_hogs[hog_id]

        raise KeyError(' Id {} cannot match any HOG Id.'.format(hog_id))

    def get_hog_by_gene(self, gene):

        """  Get the top level :obj:`HOG` that contain the query :obj:`Gene`. If the :obj:`Gene` is a singleton it will 
        return itself.

            Args:
                gene (:obj:`Gene`): :obj:`Gene` object.

            Returns:
                :obj:`HOG` or raise KeyError

        """

        if isinstance(gene, abstractgene.Gene):
            return gene.get_top_level_hog()

        raise KeyError("expect a '{}' as query, got {}".format(abstractgene.Gene, type(gene).__name__))

    def get_list_top_level_hogs(self):

        """  Get the list of all the top level :obj:`HOG`.

            Returns:
                a list of :obj:`HOG`.

        """

        return list(self.top_level_hogs.values())

    def get_dict_top_level_hogs(self):

        """  Get a dictionary that map all top level hog id with their related :obj:`HOG`.

            Returns:
                a dictionary mapping hog Id (:obj:`str`) with :obj:`HOG`.

        """

        return self.top_level_hogs

    # ___ ExtantGenome ___ #

    def get_list_extant_genomes(self):

        """  
        Get the list of all :obj:`ExtantGenome` created during the parsing.

            Returns:
                a list of :obj:`ExtantGenome`.

        """

        return [leaf.genome for leaf in self.taxonomy.leaves]

    def get_extant_genome_by_name(self, name):

        """  
        Get the :obj:`ExtantGenome` that match the query name.

            Args:
                name (:obj:`str`): Name of the :obj:`ExtantGenome`.

            Returns:
                :obj:`ExtantGenome` or raise KeyError

        """

        for taxon in self.taxonomy.leaves:
            if taxon.name == name:
                if "genome" in taxon.features:
                    return taxon.genome

        raise KeyError('No extant genomes match the query name: {}'.format(name))

    # ___ AncestralGenome ___ #

    def get_list_ancestral_genomes(self):

        """  
            Get the list of all :obj:`AncestralGenome` created during the parsing.

            Returns:
                a list of :obj:`AncestralGenome`.

        """
        return [internal_node.genome for internal_node in self.taxonomy.internal_nodes]

    def get_ancestral_genome_by_taxon(self, taxon):

        """  
        Get the :obj:`AncestralGenome` corresponding of the query taxon.

            Args:
                taxon (:obj:`str`): treeNode object of the :obj:`Taxonomy`.tree object.

            Returns:
                :obj:`AncestralGenome` or raise KeyError

        """

        if taxon in self.taxonomy.internal_nodes and "genome" in taxon.features:
                return taxon.genome

        raise KeyError("Taxon {} doesn't have a genome attached to it.".format(taxon))

    def get_ancestral_genome_by_name(self, name):

        """  
        Get the :obj:`AncestralGenome` corresponding of the query name.

            Args:
                name (:obj:`str`): Name of the :obj:`AncestralGenome`.

            Returns:
                :obj:`AncestralGenome` or raise KeyError

        """

        for taxon in self.taxonomy.internal_nodes:
            if taxon.name == name:
                if "genome" in taxon.features:
                    return taxon.genome

        raise KeyError('No ancestral genomes match the query name: {}'.format(name))

    def get_ancestral_genome_by_mrca_of_genome_set(self, genome_set):

        """  
        Get the :obj:`AncestralGenome` corresponding to the MRCA of query genomes.

            Args:
                genome_set (:obj:`set`): Set of :obj:`AncestralGenome`.

            Returns:
                :obj:`AncestralGenome` or raise KeyError

        """

        if len(genome_set) < 2:
            raise ValueError('Minimum 2 genomes are required, only {} provided.'.format(len(genome_set)))

        for g in genome_set:
            if not isinstance(g, genome.Genome):
                raise TypeError("expect subclass obj of '{}', got {}"
                                .format(genome.Genome.__name__,
                                        type(g).__name__))

        genome_nodes = set([genome.taxon for genome in genome_set])

        mrca_node = self.taxonomy.tree.get_common_ancestor(genome_nodes)

        return self.get_ancestral_genome_by_taxon(mrca_node)

    # Taxon

    def get_taxon_by_name(self, name):

        """  
        Get the treeNode object of the :obj:`Taxonomy`.tree corresponding of the query name.

            Args:
                name (:obj:`str`): Name of the treeNode.

            Returns:
                treeNode or raise KeyError

        """

        nodes_founded = self.taxonomy.tree.search_nodes(name=name)

        if not nodes_founded:
            raise KeyError('No node founded for the species name: {}'.format(name))
        elif len(nodes_founded) == 1:
            return nodes_founded[0]
        else:
            raise KeyError('{} nodes founded for the species name: {}'.format(len(nodes_founded), name))

    # ... PRIVATE METHODS ... #

    def _add_missing_taxon(self, child_hog, oldest_hog, missing_taxons):

        """  
        Add intermediate :obj:`HOG` in between two :obj:`HOG` if their taxon are not direct parent and child in the 
        taxonomy. E.g. if a rodent HOG is connected with a vertebrate HOG it will add an mammal hog in between.

            Args:
                child_hog (:obj:`HOG`): child :obj:`HOG`.
                oldest_hog (:obj:`HOG`): parent :obj:`HOG`.
                missing_taxons (:obj:`HOG`): list of intermediate taxNode between child_hog and oldest_hog sorted 
                from youngest to oldest.

        """

        if not isinstance(child_hog, abstractgene.AbstractGene):
            raise TypeError("expect subclass obj of '{}', got {}"
                            .format(abstractgene.AbstractGene.__name__,
                                    type(child_hog).__name__))

        if not isinstance(oldest_hog, abstractgene.AbstractGene):
            raise TypeError("expect subclass obj of '{}', got {}"
                            .format(abstractgene.AbstractGene.__name__,
                                    type(oldest_hog).__name__))

        if oldest_hog == child_hog:
            raise TypeError("Cannot add missing level between an HOG and it self.")

        # the youngest hog is removed from the oldest hog children.
        oldest_hog.remove_child(child_hog)

        # Then for each intermediate level in between the two hogs...
        current_child = child_hog
        for tax in missing_taxons:

            # ... we get the related ancestral genome of this level...
            ancestral_genome = self._get_ancestral_genome_by_taxon(tax)

            # ... we create the related hog and add it to the ancestral genome...
            hog = abstractgene.HOG()
            hog.set_genome(ancestral_genome)
            ancestral_genome.add_gene(hog)

            # ... we check if taxon correspond to child parent taxon ...
            if ancestral_genome.taxon is not current_child.genome.taxon.up:
                raise TypeError("HOG taxon {} is different than child parent taxon {}".format(ancestral_genome.taxon,
                                                                                              current_child.genome.taxon.up))

            # ... we add the child if everything is fine.
            hog.add_child(current_child)
            current_child = hog

        oldest_hog.add_child(current_child)

    def _get_oldest_from_genome_pair(self, g1, g2):

        """  
        Get the oldest :obj:`Genome` for a pair of :obj:`Genome`.

            Args:
                g1 (:obj:`Genome`): First :obj:`Genome`.
                g2 (:obj:`Genome`): Second :obj:`Genome`.

            Returns:
                :obj:`Genome`

        """

        mrca = self.taxonomy.tree.get_common_ancestor({g1,g2})

        if g1 == mrca:
            return g1, g2
        elif g2 == mrca:
            return g2, g1
        else:
            raise TypeError("The genomes are not in the same lineage: {}".format({g1, g2}))

    def _get_ancestor_and_descendant(self, genome_set):

        """  
        This method fetch from a set of :obj:`Genome`:
            - the oldest :obj:`Genome` from the set (if oldest genome not in set we get their mrca ).
            - the rest of the :obj:`Genome` present in the set.

            Args:
                genome_set (:obj:`set`): A set of :obj:`Genome`.

            Returns:
                :obj:`Genome`, a set of :obj:`Genome`.

        """

        ancestor = self._get_ancestral_genome_by_mrca_of_genome_set(genome_set)
        genome_set.discard(ancestor)
        return ancestor, genome_set

    def _get_HOGMap(self, genome_pair_set):

        """ 
        Get the :obj:`HOGMap` between two genomes.
        
            Args:
                genome_pair_set (:obj:`set`): A set of 2 :obj:`Genome`.

            Returns:
                :obj:`HOGMap`

        """

        f = frozenset(genome_pair_set)

        if f in self.HOGMaps.keys():
            return self.HOGMaps[f]
        else:
            self.HOGMaps[f] = mapper.HOGsMap(self, genome_pair_set)
            return self.HOGMaps[f]

    def _build_hogs_and_genes(self, file_object, filter_object):

        """ This function build from an orthoxml file all data that is required to build this HAM object (using the HAM
        filter object).

            Args:
                file_object (:obj:`FileObject`): File Object of the orthoxml to parse.
                filter_object (:obj:`ParserFilter`): :obj:`ParserFilter` use by OrthoXMLParser.

            Returns:
                :obj:`set` of top level :obj:`HOG` , :obj:`dict` of unique id with their :obj:`Gene`, :obj:`dict` of
                external id with their :obj:`Gene`.

        """

        factory = parsers.OrthoXMLParser(self, filterObject=filter_object)
        parser = XMLParser(target=factory)

        for line in file_object:
            parser.feed(line)

        return factory.toplevel_hogs, factory.extant_gene_map, factory.external_id_mapper

    def _get_extant_genome_by_name(self, **kwargs):

        """ 
        Get the :obj:`ExtantGenome` by name, if not founded in the taxonomy.tree.node.genome then created it.

            Args:
                **kwargs: dictionary of attribute and value required to create the :obj:`ExtantGenome`.

            Returns:
                :obj:`ExtantGenome`

        """

        nodes_founded = self.taxonomy.tree.search_nodes(name=kwargs['name'])

        if len(nodes_founded) == 1:

            node = nodes_founded[0]

            if "genome" in node.features:
                return node.genome

            else:
                extant_genome = genome.ExtantGenome(**kwargs)
                self.taxonomy.add_genome_to_node(node, extant_genome)
                return extant_genome
        else:
            raise KeyError('{} node(s) founded for the species name: {}'.format(len(nodes_founded), kwargs['name']))

    def _get_ancestral_genome_by_taxon(self, tax_node):

        """  
        Get the :obj:`AncestralGenome` corresponding of the query taxon if not founded in the taxonomy.tree
        then created it.

            Args:
                tax_node : treeNode object of the :obj:`Taxonomy`.tree object.

            Returns:
                :obj:`AncestralGenome`

        """

        if "genome" in tax_node.features:
            return tax_node.genome

        else:
            ancestral_genome = genome.AncestralGenome()
            self.taxonomy.add_genome_to_node(tax_node, ancestral_genome)

            return ancestral_genome

    def _get_ancestral_genome_by_mrca_of_hog_children_genomes(self, hog):

        """  
        Get MRCA :obj:`AncestralGenome` of the list of children :obj:`Genome` of the query :obj:`HOG`.
        
            Args:
                hog (:obj:`HOG`): query HOG.
        
            Returns:
                :obj:`AncestralGenome`
        
        """

        children_genomes = set([child.genome for child in hog.children ])

        return self._get_ancestral_genome_by_mrca_of_genome_set(children_genomes)

    def _get_ancestral_genome_by_mrca_of_genome_set(self, genome_set):

        """  
        Get the :obj:`AncestralGenome` corresponding to the MRCA of query genomes.

            Args:
                genome_set (:obj:`set`): Set of :obj:`AncestralGenome`.

            Returns:
                :obj:`AncestralGenome` or raise KeyError

        """

        if len(genome_set) < 2:
            raise ValueError('Minimum 2 genomes are required, only {} provided.'.format(len(genome_set)))

        for g in genome_set:
            if not isinstance(g, genome.Genome):
                raise TypeError("expect subclass obj of '{}', got {}"
                                .format(genome.Genome.__name__,
                                        type(g).__name__))

        genome_nodes = set([genome.taxon for genome in genome_set])

        mrca_node = self.taxonomy.tree.get_common_ancestor(genome_nodes)

        return self._get_ancestral_genome_by_taxon(mrca_node)